import de.dennysubke.oniondrop.core.*;
import java.io.*;
import java.net.*;
import java.nio.charset.StandardCharsets;
import java.nio.file.Path;
import java.nio.file.Files;
import java.util.*;
import java.util.concurrent.*;

public class CoreTest {
    private static int checks;
    private static void check(boolean yes,String message){if(!yes)throw new AssertionError(message);checks++;}
    private static String request(int port,String method,String path,String headers,byte[] data)throws Exception{
        try(Socket s=new Socket("127.0.0.1",port)){
            s.setSoTimeout(4000);OutputStream out=s.getOutputStream();out.write((method+" "+path+" HTTP/1.1\r\nHost: "+"a".repeat(56)+".onion\r\n"+headers+"\r\n").getBytes(StandardCharsets.UTF_8));if(data!=null)out.write(data);out.flush();s.shutdownOutput();return new String(s.getInputStream().readAllBytes(),StandardCharsets.UTF_8);
        }
    }
    private static String get(DropServer server,String path)throws Exception{return request(server.port(),"GET",path,"",null);}
    public static void main(String[] args)throws Exception{
        Path root=Files.createTempDirectory("oniondrop-core-test");
        try{
            check(DropSecurity.token().length()==43,"token length");check(!DropSecurity.token().equals(DropSecurity.token()),"fresh tokens");
            check(DropSecurity.filename("../../secret.txt").equals("secret.txt"),"traversal name");
            check(!DropSecurity.filename("evil\r\nX-Header: yes").contains("\r"),"header injection");
            check(DropSecurity.html("<script>&\"").equals("&lt;script&gt;&amp;&quot;"),"HTML escaping");
            FileStore store=new FileStore(root.toFile());
            byte[] content="Grüße aus OnionDrop".getBytes(StandardCharsets.UTF_8);
            DropFile shared=store.importFile("report <script>.txt","text/html",content.length,new ByteArrayInputStream(content));
            check(store.shared().size()==1,"import");check(!shared.file.getName().contains("report"),"random storage filename");
            try{store.importFile("truncated.txt","text/plain",3,new ByteArrayInputStream(new byte[5]));throw new AssertionError("incorrect size accepted");}catch(IOException expected){check(store.shared().size()==1,"no truncated shared file");}
            try{store.receive("too-large",DropServer.MAX_FILE+1,new ByteArrayInputStream(new byte[0]));throw new AssertionError("oversize accepted");}catch(IOException expected){checks++;}
            try{store.receive("incomplete",8,new ByteArrayInputStream(new byte[3]));throw new AssertionError("partial accepted");}catch(IOException expected){check(store.received().isEmpty(),"partial upload not committed");}
            try(DropServer server=new DropServer(store,event->{},new byte[]{(byte)137,80,78,71})){
                server.setOnion("a".repeat(56)+".onion");server.sending.set(true);server.receiving.set(true);server.start();
                String send="/s/"+server.sendToken+"/",receive="/r/"+server.receiveToken+"/";
                check(get(server,"/").startsWith("HTTP/1.1 404"),"root hidden");
                check(get(server,"/s/wrong/").startsWith("HTTP/1.1 404"),"bad token");
                check(get(server,send.substring(0,send.length()-1)).startsWith("HTTP/1.1 303"),"canonical slash");
                String page=get(server,send);check(page.contains("report &lt;script&gt;.txt"),"escaped display name");
                check(!page.contains("report <script>"),"no filename script execution");check(page.contains("Referrer-Policy: no-referrer"),"no referrer");
                check(page.contains("Content-Security-Policy"),"content policy");
                String download=get(server,send+"file/"+shared.id);check(download.endsWith(new String(content,StandardCharsets.UTF_8)),"streamed download");
                check(download.contains("Content-Disposition: attachment"),"forced attachment");check(download.contains("application/octet-stream"),"untrusted MIME not rendered");
                check(get(server,send+"file/../../etc/passwd").startsWith("HTTP/1.1 404"),"download traversal rejected");
                check(get(server,receive+"file/"+shared.id).startsWith("HTTP/1.1 404"),"receive token cannot download");
                String upload=receive+"upload?name="+DropSecurity.encode("../../private + ü.txt");
                String headers="X-OnionDrop-Upload: 1\r\nContent-Length: "+content.length+"\r\n";
                check(request(server.port(),"POST",upload,headers,content).startsWith("HTTP/1.1 201"),"upload");
                check(store.received().size()==1,"received file");check(store.received().get(0).name.equals("private + ü.txt"),"UTF-8 name and basename");
                check(!get(server,receive).contains("private +"),"no inbox listing for remote visitors");
                check(request(server.port(),"POST",upload,"Content-Length: 0\r\n",null).startsWith("HTTP/1.1 403"),"custom header required");
                check(request(server.port(),"POST",upload,"X-OnionDrop-Upload: 1\r\nContent-Length: 0\r\nOrigin: https://evil.invalid\r\n",null).startsWith("HTTP/1.1 403"),"cross-origin rejected");
                check(request(server.port(),"POST",upload,"X-OnionDrop-Upload: 1\r\nContent-Length: 262144001\r\n",null).startsWith("HTTP/1.1 413"),"oversized request rejected before reading");
                check(request(server.port(),"POST",upload,"X-OnionDrop-Upload: 1\r\nContent-Length: 0\r\nContent-Length: 1\r\n",null).startsWith("HTTP/1.1 400"),"duplicate length rejected");
                check(request(server.port(),"POST",upload,"Transfer-Encoding: chunked\r\n",null).startsWith("HTTP/1.1 400"),"chunked rejected");
                check(request(server.port(),"POST",upload,"X-OnionDrop-Upload: 1\r\n",null).startsWith("HTTP/1.1 411"),"length required");
                check(request(server.port(),"GET",send,"X-Huge: "+"x".repeat(17000)+"\r\n",null).startsWith("HTTP/1.1 431"),"bounded headers");
                server.sending.set(false);check(get(server,send).startsWith("HTTP/1.1 404"),"disabled sharing invalidates route");
                server.receiving.set(false);check(request(server.port(),"POST",upload,headers,content).startsWith("HTTP/1.1 404"),"disabled receiver");
            }
            check(new FileStore(root.toFile()).received().size()==1,"files survive repository restart");
            store.delete(true,shared.id);check(store.shared().isEmpty(),"local deletion");
            torProtocol();
            System.out.println(checks+" core security/transfer checks passed.");
        }finally{try(java.util.stream.Stream<Path> stream=Files.walk(root)){stream.sorted(Comparator.reverseOrder()).forEach(p->{try{Files.delete(p);}catch(IOException ignored){}});}}
    }
    private static void torProtocol()throws Exception{
        List<String> events=new ArrayList<>();ExecutorService worker=Executors.newSingleThreadExecutor();
        try(ServerSocket listener=new ServerSocket(0,1,InetAddress.getByName("127.0.0.1"))){
            Future<?> fake=worker.submit(()->{try(Socket s=listener.accept();BufferedReader in=new BufferedReader(new InputStreamReader(s.getInputStream(),StandardCharsets.US_ASCII));OutputStream out=s.getOutputStream()){
                check(in.readLine().equals("AUTHENTICATE abc"),"control auth command");out.write("250 OK\r\n".getBytes(StandardCharsets.US_ASCII));out.flush();
                check(in.readLine().equals("ADD_ONION test"),"control request");
                out.write(("650 STATUS_CLIENT NOTICE BOOTSTRAP PROGRESS=100\r\n250-ServiceID="+"b".repeat(56)+"\r\n250 OK\r\n650 HS_DESC UPLOADED "+"b".repeat(56)+" NO_AUTH test\r\n").getBytes(StandardCharsets.US_ASCII));out.flush();
            }catch(Exception ex){throw new RuntimeException(ex);}});
            try(Socket s=new Socket("127.0.0.1",listener.getLocalPort());TorControl control=new TorControl(s,events::add)){
                check(control.command("AUTHENTICATE abc").get(0).equals("OK"),"auth reply");
                check(control.command("ADD_ONION test").get(0).equals("ServiceID="+"b".repeat(56)),"multiline reply");
                control.nextEvent();check(events.size()==2&&events.get(1).contains("HS_DESC UPLOADED"),"asynchronous Tor events");
                try{control.command("BAD\r\nCOMMAND");throw new AssertionError("command injection accepted");}catch(IOException expected){checks++;}
            }fake.get(5,TimeUnit.SECONDS);
        }finally{worker.shutdownNow();}
    }
}
