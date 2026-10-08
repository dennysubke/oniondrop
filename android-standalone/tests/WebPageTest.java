import de.dennysubke.oniondrop.core.*;
import static de.dennysubke.oniondrop.core.WebText.Key.*;
import java.io.*;
import java.net.Socket;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.*;
import java.util.concurrent.atomic.AtomicReference;

public final class WebPageTest {
    private static int checks;
    private static void check(boolean result,String message){if(!result)throw new AssertionError(message);checks++;}
    private static String request(DropServer server,String method,String path,String extra,byte[] body)throws Exception{
        try(Socket socket=new Socket("127.0.0.1",server.port())){
            socket.setSoTimeout(4000);
            OutputStream out=socket.getOutputStream();
            out.write((method+" "+path+" HTTP/1.1\r\nHost: "+"a".repeat(56)+".onion\r\n"+extra+"\r\n").getBytes(StandardCharsets.UTF_8));
            if(body!=null)out.write(body);
            out.flush();socket.shutdownOutput();
            String response=new String(socket.getInputStream().readAllBytes(),StandardCharsets.UTF_8);
            String[] parts=response.split("\r\n\r\n",2);
            if(!method.equals("HEAD")){
                int declared=Integer.parseInt(parts[0].split("Content-Length: ")[1].split("\r\n")[0]);
                check(parts[1].getBytes(StandardCharsets.UTF_8).length==declared,"UTF-8 Content-Length");
            }
            return response;
        }
    }
    private static void error(DropServer server,String method,String path,String headers,int status,WebText text,WebText.Key key)throws Exception{
        String response=request(server,method,path,headers,null);
        check(response.startsWith("HTTP/1.1 "+status+" "),"status: "+key);
        check(response.endsWith("\r\n\r\n"+text.get(key)),text.language+": localized "+key);
    }
    public static void main(String[] args)throws Exception{
        Path root=Files.createTempDirectory("oniondrop-web-test");
        Path pages=args.length>0?Path.of(args[0]):null;
        if(pages!=null)Files.createDirectories(pages);
        List<String> events=new ArrayList<>();
        try{
            FileStore store=new FileStore(root.toFile());
            byte[] content="A file with UTF-8: ä 日本語".getBytes(StandardCharsets.UTF_8);
            DropFile shared=store.importFile("report <script> ' & ü.txt","text/plain",content.length,new ByteArrayInputStream(content));
            AtomicReference<WebText> messages=new AtomicReference<>(TestMessages.load("en"));
            try(DropServer server=new DropServer(store,events::add,new byte[]{1},messages::get)){
                server.setOnion("a".repeat(56)+".onion");server.sending.set(true);server.receiving.set(true);server.start();
                String send="/s/"+server.sendToken+"/",receive="/r/"+server.receiveToken+"/";
                String upload=receive+"upload?name=test.txt";
                String script=null;
                for(String language:new String[]{"en","de","es","fr","it","ru","zh","ja"}){
                    WebText text=TestMessages.load(language);messages.set(text);
                    String sendPage=request(server,"GET",send,"",null);
                    String receivePage=request(server,"GET",receive,"",null);
                    for(String page:new String[]{sendPage,receivePage}){
                        check(page.contains("<html lang=\""+language+"\">"),language+": HTML language");
                        check(page.contains("Content-Language: "+language+"\r\n"),language+": response language");
                        check(page.contains(text.html(FOOTER)),language+": footer");
                        check(page.contains("default-src 'none'")&&page.contains("Referrer-Policy: no-referrer"),"privacy headers retained");
                    }
                    for(WebText.Key key:new WebText.Key[]{SEND_TITLE,SEND_DESCRIPTION,SAVE_FILE,BYTES})check(sendPage.contains(text.html(key)),language+": send "+key);
                    for(WebText.Key key:new WebText.Key[]{RECEIVE_TITLE,RECEIVE_DESCRIPTION,CHOOSE_FILES,SEND_FILES,JAVASCRIPT_REQUIRED,SELECT_FILES,TOO_LARGE,SENDING,TRANSFER_FAILED,FILES_SENT,NETWORK_FAILED})check(receivePage.contains(text.html(key)),language+": receive "+key);
                    check(sendPage.contains(DropSecurity.html(shared.name)),"filename remains escaped");
                    String body=receivePage.split("\r\n\r\n",2)[1];
                    if(pages!=null){Files.writeString(pages.resolve(language+"-receive.html"),body);Files.writeString(pages.resolve(language+"-send.html"),sendPage.split("\r\n\r\n",2)[1]);}
                    String currentScript=body.substring(body.indexOf("<script nonce="));
                    currentScript=currentScript.substring(currentScript.indexOf('>')+1,currentScript.indexOf("</script>"));
                    if(script==null)script=currentScript;
                    check(script.equals(currentScript),"translations never enter JavaScript source");
                    check(request(server,"HEAD",receive,"",null).endsWith("\r\n\r\n"),"HEAD has no body");
                    error(server,"GET","/","",404,text,NOT_FOUND);
                    error(server,"DELETE",send,"",405,text,METHOD_NOT_ALLOWED);
                    error(server,"GET",send+"file/missing","",404,text,FILE_NOT_FOUND);
                    error(server,"POST",upload,"Content-Length: 0\r\n",403,text,UPLOAD_HEADER_REQUIRED);
                    error(server,"POST",upload,"X-OnionDrop-Upload: 1\r\n",411,text,LENGTH_REQUIRED);
                    error(server,"POST",upload,"X-OnionDrop-Upload: 1\r\nContent-Length: 262144001\r\n",413,text,MAX_FILE_SIZE);
                    error(server,"POST",receive+"upload","X-OnionDrop-Upload: 1\r\nContent-Length: 0\r\n",400,text,NAME_REQUIRED);
                    error(server,"POST",upload,"X-OnionDrop-Upload: 1\r\nContent-Length: 0\r\nOrigin: https://evil.invalid\r\n",403,text,ORIGIN_NOT_ALLOWED);
                    error(server,"POST",upload,"Content-Length: 0\r\nContent-Length: 1\r\n",400,text,DUPLICATE_HEADER);
                    error(server,"POST",upload,"Content-Length: nope\r\n",400,text,INVALID_LENGTH);
                    error(server,"GET",send,"Invalid header\r\n",400,text,INVALID_HEADER);
                    error(server,"GET",send,"X-Huge: "+"x".repeat(17000)+"\r\n",431,text,HEADERS_TOO_LARGE);
                    error(server,"POST",upload,"Transfer-Encoding: chunked\r\n",400,text,CHUNKED_UNSUPPORTED);
                    error(server,"POST",upload,"Expect: 100-continue\r\n",417,text,EXPECT_UNSUPPORTED);
                    error(server,"GET","/%bad[","",400,text,INVALID_PATH);
                    error(server,"GET","https://example.invalid","",400,text,INVALID_REQUEST);
                    String redirect=request(server,"GET",send.substring(0,send.length()-1),"",null);
                    check(redirect.startsWith("HTTP/1.1 303")&&redirect.endsWith(text.get(REDIRECT)),"localized redirect");
                    String received=request(server,"POST",upload,"X-OnionDrop-Upload: 1\r\nContent-Length: "+content.length+"\r\n",content);
                    check(received.startsWith("HTTP/1.1 201"),language+": upload still works");
                    check(request(server,"GET",send+"file/"+shared.id,"",null).endsWith(new String(content,StandardCharsets.UTF_8)),language+": download unchanged");
                }
                check(store.received().size()==8,"all localized uploads saved");
                messages.set(TestMessages.load("en"));
                check(request(server,"GET",receive,"",null).contains("<html lang=\"en\">"),"language switch affects existing session");
                EnumMap<WebText.Key,String> hostile=new EnumMap<>(WebText.Key.class);
                WebText english=TestMessages.load("en");
                for(WebText.Key key:WebText.Key.values())hostile.put(key,english.get(key));
                hostile.put(SELECT_FILES,"'\"><script>alert(1)</script>&");
                messages.set(new WebText("en",hostile));
                String escaped=request(server,"GET",receive,"",null);
                check(!escaped.contains("<script>alert(1)"),"translation cannot inject markup");
                check(escaped.contains("&#39;&quot;&gt;&lt;script&gt;alert(1)&lt;/script&gt;&amp;"),"attribute escaping");
            }
            System.out.println(checks+" localized page, status, error and transfer checks passed.");
        }finally{try(java.util.stream.Stream<Path> files=Files.walk(root)){files.sorted(Comparator.reverseOrder()).forEach(p->{try{Files.delete(p);}catch(IOException ignored){}});}}
    }
}
