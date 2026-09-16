package de.dennysubke.oniondrop.core;

import java.io.*;
import java.net.*;
import java.nio.charset.StandardCharsets;
import java.util.*;
import java.util.concurrent.*;
import java.util.concurrent.atomic.AtomicBoolean;

/** HTTP is loopback-only. Tor is the only network-facing transport. No remote administration. */
public final class DropServer implements AutoCloseable {
    public interface Repository {
        List<DropFile> shared();
        DropFile receive(String name,long length,InputStream source) throws IOException;
    }
    public interface Listener {void changed(String event);}
    public static final long MAX_FILE=250L*1024*1024;
    private final Repository repository;
    private final Listener listener;
    private final byte[] logo;
    public final String sendToken=DropSecurity.token(),receiveToken=DropSecurity.token();
    public final AtomicBoolean sending=new AtomicBoolean(false),receiving=new AtomicBoolean(false);
    private final ServerSocket server;
    private final Set<Socket> sockets=ConcurrentHashMap.newKeySet();
    private final ThreadPoolExecutor workers=new ThreadPoolExecutor(4,4,0,TimeUnit.SECONDS,new ArrayBlockingQueue<>(8),r->{Thread t=new Thread(r,"oniondrop-http");t.setDaemon(true);return t;});
    private volatile boolean closed;
    private volatile String host="";
    public DropServer(Repository repository,Listener listener,byte[] logo) throws IOException {
        this.repository=repository;this.listener=listener;this.logo=logo;
        server=new ServerSocket();server.bind(new InetSocketAddress(InetAddress.getByName("127.0.0.1"),0),16);
    }
    public int port(){return server.getLocalPort();}
    public void setOnion(String value){if(!value.matches("[a-z2-7]{56}\\.onion"))throw new IllegalArgumentException("Invalid onion host");host=value;}
    public void start(){Thread t=new Thread(()->{while(!closed){try{Socket s=server.accept();s.setSoTimeout(60000);sockets.add(s);try{workers.execute(()->serve(s));}catch(RejectedExecutionException ex){sockets.remove(s);s.close();}}catch(IOException ex){if(!closed)listener.changed("Verbindung unterbrochen");}}},"oniondrop-listener");t.setDaemon(true);t.start();}
    private void serve(Socket socket){
        try(Socket s=socket;InputStream in=new BufferedInputStream(s.getInputStream());OutputStream out=new BufferedOutputStream(s.getOutputStream())){
            Request r;
            try{r=Request.read(in);}catch(BadRequest ex){reply(out,ex.code,"text/plain; charset=utf-8",ex.getMessage().getBytes(StandardCharsets.UTF_8),false,null);return;}
            if(!host.isEmpty()&&!DropSecurity.equal(host,r.headers.get("host"))){replyText(out,400,"Ungültiger Host.");return;}
            if(!r.method.equals("GET")&&!r.method.equals("HEAD")&&!r.method.equals("POST")){replyText(out,405,"Methode nicht erlaubt.");return;}
            String[] bits=r.path.split("/",-1);
            if(bits.length<3){replyText(out,404,"Nicht gefunden.");return;}
            boolean send=bits[1].equals("s")&&sending.get()&&DropSecurity.equal(sendToken,bits[2]);
            boolean receive=bits[1].equals("r")&&receiving.get()&&DropSecurity.equal(receiveToken,bits[2]);
            if(!send&&!receive){replyText(out,404,"Nicht gefunden.");return;}
            if(bits.length==3 && (r.method.equals("GET")||r.method.equals("HEAD"))){
                byte[] body="Weiterleitung".getBytes(StandardCharsets.UTF_8);
                reply(out,303,"text/plain",body,r.method.equals("HEAD"),"Location: "+r.path+"/\r\n");return;
            }
            String action=bits.length==4?bits[3]:"";
            if(bits.length==4&&action.equals("logo.png")&&(r.method.equals("GET")||r.method.equals("HEAD"))){reply(out,200,"image/png",logo,r.method.equals("HEAD"),null);return;}
            if(bits.length==4&&action.isEmpty()&&(r.method.equals("GET")||r.method.equals("HEAD"))){
                String page=send?sendPage():receivePage();reply(out,200,"text/html; charset=utf-8",page.getBytes(StandardCharsets.UTF_8),r.method.equals("HEAD"),null);return;
            }
            if(send&&bits.length==5&&bits[3].equals("file")&&(r.method.equals("GET")||r.method.equals("HEAD"))){
                DropFile file=null;for(DropFile f:repository.shared())if(DropSecurity.equal(f.id,bits[4])){file=f;break;}
                if(file==null||!file.file.isFile()){replyText(out,404,"Datei nicht gefunden.");return;}
                // Hold the stream before promising a complete response; never serve user MIME inline.
                try(InputStream src=new FileInputStream(file.file)){
                    headers(out,200,"application/octet-stream",file.size,"Content-Disposition: attachment; filename*=UTF-8''"+DropSecurity.encode(file.name)+"\r\n");
                    if(!r.method.equals("HEAD")){copy(src,out,file.size);listener.changed("Datei abgerufen");}out.flush();
                }return;
            }
            if(receive&&bits.length==4&&action.equals("upload")&&r.method.equals("POST")){
                String origin=r.headers.get("origin");
                if(origin!=null&&!origin.equals("http://"+host)){replyText(out,403,"Ursprung nicht erlaubt.");return;}
                if(!"1".equals(r.headers.get("x-oniondrop-upload"))){replyText(out,403,"Upload-Header fehlt.");return;}
                if(r.length<0){replyText(out,411,"Content-Length erforderlich.");return;}
                if(r.length>MAX_FILE){replyText(out,413,"Maximal 250 MiB pro Datei.");return;}
                String name=r.query.get("name");if(name==null||name.length()>1024){replyText(out,400,"Dateiname fehlt.");return;}
                try{
                    repository.receive(DropSecurity.filename(name),r.length,in);
                    reply(out,201,"application/json","{\"ok\":true}".getBytes(StandardCharsets.UTF_8),false,null);listener.changed("Datei empfangen");
                }catch(IOException ex){replyText(out,507,"Datei konnte nicht vollständig gespeichert werden. Speicherlimit oder Übertragung prüfen.");}
                return;
            }
            replyText(out,404,"Nicht gefunden.");
        }catch(IOException ignored){/* Client disconnects never become content or secret-bearing logs. */}
        finally{sockets.remove(socket);}
    }
    private static void copy(InputStream in,OutputStream out,long length)throws IOException{byte[] b=new byte[32768];while(length>0){int n=in.read(b,0,(int)Math.min(b.length,length));if(n<0)throw new EOFException("Unvollständige Datei");out.write(b,0,n);length-=n;}}
    private String shell(String title,String content,String script){
        String nonce=DropSecurity.token();
        // Per-page CSP nonce, no remote assets, cookies, fonts, analytics or upload history.
        return "<!doctype html><html lang=\"de\"><meta charset=\"utf-8\"><meta name=\"viewport\" content=\"width=device-width,initial-scale=1\">"+
            "<meta http-equiv=\"Content-Security-Policy\" content=\"default-src 'none'; img-src 'self'; style-src 'unsafe-inline'; script-src 'nonce-"+nonce+"'; connect-src 'self'; base-uri 'none'; form-action 'none'\">"+
            "<title>"+title+" · OnionDrop</title><style>body{background:#100c19;color:#f6f0ff;font:16px/1.6 system-ui;margin:0;padding:30px 20px}main{max-width:560px;margin:5vh auto}header{display:flex;align-items:center;gap:12px;font-weight:650}img{width:46px;height:46px}h1{font-size:32px;line-height:1.2;margin-top:36px}p,small{color:#b6aac8}a,button{display:block;background:#c49bff;color:#20112d;border:0;border-radius:16px;padding:16px;text-decoration:none;font:600 16px system-ui;overflow-wrap:anywhere}article{background:#20172d;border-radius:20px;padding:18px;margin:16px 0}article a{background:#352242;color:#dfc7ff;padding:12px;margin-top:14px}input{width:100%;margin:20px 0}progress{width:100%;accent-color:#c49bff}button:disabled{opacity:.5}</style><main><header><img src=\"logo.png\" alt=\"\">OnionDrop</header><h1>"+title+"</h1>"+content+"<p><small>Direkt vom Gerät. Über Tor. Der Link gilt nur während der aktiven Freigabe.</small></p></main>"+(script.isEmpty()?"":"<script nonce=\""+nonce+"\">"+script+"</script>")+"</html>";
    }
    private String sendPage(){StringBuilder c=new StringBuilder("<p>Diese Dateien wurden für dich freigegeben.</p>");for(DropFile f:repository.shared())c.append("<article><strong>").append(DropSecurity.html(f.name)).append("</strong><br><small>").append(f.size).append(" Bytes</small><a href=\"file/").append(f.id).append("\" download>Datei speichern</a></article>");return shell("Ein Drop für dich.",c.toString(),"");}
    private String receivePage(){return shell("Privat abgeben.","<p>Wähle Dateien aus. Sie werden direkt auf dem Gerät des Empfängers gespeichert. Maximal 250 MiB je Datei.</p><article><input id=\"files\" type=\"file\" multiple aria-label=\"Dateien auswählen\"><button id=\"send\">Dateien senden</button><p id=\"status\" role=\"status\" aria-live=\"polite\"></p></article><noscript>Für den Upload muss JavaScript im Tor Browser aktiviert sein.</noscript>",
        "const picker=document.getElementById('files'),button=document.getElementById('send'),status=document.getElementById('status');button.onclick=async()=>{if(!picker.files.length){status.textContent='Bitte Dateien auswählen.';return;}button.disabled=true;picker.disabled=true;let completed=0;try{for(const file of picker.files){if(file.size>262144000)throw Error('Datei zu groß: '+file.name);status.textContent='Wird gesendet: '+file.name;const r=await fetch('upload?name='+encodeURIComponent(file.name),{method:'POST',headers:{'X-OnionDrop-Upload':'1','Content-Type':'application/octet-stream'},body:file,credentials:'omit',redirect:'error'});if(!r.ok)throw Error('Übertragung fehlgeschlagen: '+file.name+' (HTTP '+r.status+')');completed++;}status.textContent=completed+' Datei(en) übermittelt.';picker.value='';}catch(e){status.textContent=completed+' Datei(en) übermittelt. '+e.message;}finally{button.disabled=false;picker.disabled=false;}};");}
    private static void replyText(OutputStream out,int status,String body)throws IOException{reply(out,status,"text/plain; charset=utf-8",body.getBytes(StandardCharsets.UTF_8),false,null);}
    private static void reply(OutputStream out,int status,String type,byte[] data,boolean head,String extra)throws IOException{headers(out,status,type,data.length,extra);if(!head)out.write(data);out.flush();}
    private static void headers(OutputStream out,int status,String type,long length,String extra)throws IOException{
        String reason=status==200?"OK":status==201?"Created":status==303?"See Other":"Error";
        String h="HTTP/1.1 "+status+" "+reason+"\r\nContent-Type: "+type+"\r\nContent-Length: "+length+"\r\nConnection: close\r\nCache-Control: no-store\r\nReferrer-Policy: no-referrer\r\nX-Content-Type-Options: nosniff\r\nX-Frame-Options: DENY\r\nPermissions-Policy: camera=(), microphone=(), geolocation=()\r\n"+(extra==null?"":extra)+"\r\n";
        out.write(h.getBytes(StandardCharsets.US_ASCII));
    }
    @Override public void close(){closed=true;sending.set(false);receiving.set(false);try{server.close();}catch(IOException ignored){}for(Socket socket:sockets)try{socket.close();}catch(IOException ignored){}workers.shutdownNow();}
    private static final class BadRequest extends IOException{final int code;BadRequest(int code,String message){super(message);this.code=code;}}
    private static final class Request {
        String method,path;long length=-1;Map<String,String> headers=new HashMap<>(),query=new HashMap<>();
        static Request read(InputStream in)throws IOException{
            ByteArrayOutputStream bytes=new ByteArrayOutputStream();int matched=0;
            byte[] end={'\r','\n','\r','\n'};
            while(matched<4){int c=in.read();if(c<0)throw new EOFException();bytes.write(c);if(bytes.size()>16384)throw new BadRequest(431,"Header zu groß.");matched=c==end[matched]?matched+1:(c=='\r'?1:0);}
            String header=new String(bytes.toByteArray(),StandardCharsets.ISO_8859_1);String[] lines=header.split("\r\n");String[] first=lines[0].split(" ");
            if(first.length!=3||!first[1].startsWith("/")||!first[2].equals("HTTP/1.1"))throw new BadRequest(400,"Ungültige Anfrage.");
            Request r=new Request();r.method=first[0];
            for(int i=1;i<lines.length;i++){int n=lines[i].indexOf(':');if(n<1)throw new BadRequest(400,"Ungültiger Header.");String key=lines[i].substring(0,n).toLowerCase(Locale.ROOT);String value=lines[i].substring(n+1).trim();if(!key.matches("[a-z0-9-]+")||r.headers.put(key,value)!=null)throw new BadRequest(400,"Doppelter oder ungültiger Header.");}
            if(r.headers.containsKey("transfer-encoding"))throw new BadRequest(400,"Chunked Upload wird nicht unterstützt.");
            if(r.headers.containsKey("expect"))throw new BadRequest(417,"Expect wird nicht unterstützt.");
            if(r.headers.containsKey("content-length")){try{String value=r.headers.get("content-length");if(!value.matches("[0-9]{1,12}"))throw new NumberFormatException();r.length=Long.parseLong(value);}catch(NumberFormatException ex){throw new BadRequest(400,"Ungültige Länge.");}}
            try{URI uri=URI.create(first[1]);if(uri.getRawAuthority()!=null||uri.getRawFragment()!=null)throw new IllegalArgumentException();r.path=uri.getRawPath();String raw=uri.getRawQuery();if(raw!=null)for(String part:raw.split("&")){String[] kv=part.split("=",2);if(kv.length==2)r.query.put(URLDecoder.decode(kv[0],"UTF-8"),URLDecoder.decode(kv[1],"UTF-8"));}}
            catch(IllegalArgumentException ex){throw new BadRequest(400,"Ungültiger Pfad.");}
            return r;
        }
    }
}
