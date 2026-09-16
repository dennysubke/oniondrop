package de.dennysubke.oniondrop.core;

import java.io.*;
import java.net.*;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.util.*;
import java.util.regex.*;

/** Runs the APK-bundled Tor executable. No system Tor, Orbot, or external server. */
public final class TorRunner implements Closeable {
    public interface Listener{void progress(int percent);void published(String host);void failed(String message);}
    private volatile Process process;private volatile TorControl control;private volatile boolean closed;
    private volatile String onionId="",uploadedId="";private volatile boolean uploaded,bootstrapped,announced;
    private final Listener listener;
    public TorRunner(Listener listener){this.listener=listener;}
    public void run(File executable,File data,int ownerPid,int httpPort){
        try{
            if(!executable.canExecute())throw new IOException("Die eingebettete Tor-Binärdatei fehlt oder ist nicht ausführbar.");
            if(!data.isDirectory()&&!data.mkdirs())throw new IOException("Tor-Verzeichnis nicht verfügbar.");
            data.setReadable(false,false);data.setWritable(false,false);data.setExecutable(false,false);data.setReadable(true,true);data.setWritable(true,true);data.setExecutable(true,true);
            File portFile=new File(data,"control-port"),cookie=new File(data,"control_auth_cookie");Files.deleteIfExists(portFile.toPath());Files.deleteIfExists(cookie.toPath());
            List<String> args=Arrays.asList(executable.getAbsolutePath(),"--DataDirectory",data.getAbsolutePath(),"--SocksPort","0","--ControlPort","127.0.0.1:auto","--ControlPortWriteToFile",portFile.getAbsolutePath(),"--CookieAuthentication","1","--CookieAuthFile",cookie.getAbsolutePath(),"--RunAsDaemon","0","--AvoidDiskWrites","1","--SafeLogging","1","--Log","notice stdout","--__OwningControllerProcess",Integer.toString(ownerPid));
            synchronized(this){if(closed)return;process=new ProcessBuilder(args).redirectErrorStream(true).start();}
            final Process child=process;
            Thread drain=new Thread(()->{try(BufferedReader log=new BufferedReader(new InputStreamReader(child.getInputStream(),StandardCharsets.UTF_8))){while(log.readLine()!=null){/* Drain; never persist circuit or address logs. */}}catch(IOException ignored){}},"oniondrop-tor-log");drain.setDaemon(true);drain.start();
            long deadline=System.currentTimeMillis()+30000;
            while(!closed&&(!portFile.isFile()||cookie.length()!=32)){if(!child.isAlive())throw new IOException("Tor konnte nicht gestartet werden.");if(System.currentTimeMillis()>deadline)throw new IOException("Tor-Steuerung antwortet nicht.");Thread.sleep(100);}
            if(closed)return;
            String portLine=new String(Files.readAllBytes(portFile.toPath()),StandardCharsets.US_ASCII).trim();Matcher pm=Pattern.compile("PORT=127\\.0\\.0\\.1:([0-9]{1,5})").matcher(portLine);
            if(!pm.matches())throw new IOException("Ungültiger lokaler Tor-Port.");
            Socket socket=new Socket();socket.connect(new InetSocketAddress("127.0.0.1",Integer.parseInt(pm.group(1))),5000);socket.setSoTimeout(1000);
            synchronized(this){if(closed){socket.close();return;}control=new TorControl(socket,this::event);}
            // Authenticate only with the cookie from private app storage.
            socket.setSoTimeout(10000);control.command("AUTHENTICATE "+DropSecurity.hex(Files.readAllBytes(cookie.toPath())));
            control.command("SETEVENTS STATUS_CLIENT HS_DESC");
            for(String reply:control.command("GETINFO status/bootstrap-phase"))event(reply);
            List<String> reply=control.command("ADD_ONION NEW:ED25519-V3 Flags=DiscardPK Port=80,127.0.0.1:"+httpPort);
            for(String line:reply)if(line.startsWith("ServiceID="))onionId=line.substring(10);
            if(!onionId.matches("[a-z2-7]{56}"))throw new IOException("Tor hat keine gültige Onion-Adresse erzeugt.");
            announce();
            socket.setSoTimeout(1000);long publishDeadline=System.currentTimeMillis()+240000;
            while(!closed){try{control.nextEvent();}catch(SocketTimeoutException ignored){}if(!announced&&System.currentTimeMillis()>publishDeadline)throw new IOException("Tor konnte die Freigabe noch nicht veröffentlichen. Prüfe dein Netzwerk und versuche es erneut.");if(!child.isAlive())throw new IOException("Tor wurde unerwartet beendet.");}
        }catch(Exception ex){if(!closed)listener.failed(ex.getMessage()==null?"Tor-Verbindung fehlgeschlagen.":ex.getMessage());}
        finally{close();}
    }
    private void event(String line){
        Matcher m=Pattern.compile("(?:PROGRESS=)([0-9]{1,3})").matcher(line);if(m.find()){int n=Math.min(100,Integer.parseInt(m.group(1)));bootstrapped=n==100;listener.progress(n);}
        if(line.startsWith("650 HS_DESC UPLOADED ")){String[] tokens=line.split(" ");if(tokens.length>3)uploadedId=tokens[3];}
        if(line.contains(" CIRCUIT_NOT_ESTABLISHED")){bootstrapped=false;announced=false;listener.progress(0);}
        if(line.contains(" CIRCUIT_ESTABLISHED"))bootstrapped=true;
        announce();
    }
    private void announce(){
        uploaded=!onionId.isEmpty()&&onionId.equals(uploadedId);
        if(bootstrapped&&uploaded&&!announced){announced=true;listener.published(onionId+".onion");}
    }
    @Override public synchronized void close(){if(closed)return;closed=true;if(control!=null)try{control.close();}catch(IOException ignored){}if(process!=null){process.destroy();try{if(!process.waitFor(2,java.util.concurrent.TimeUnit.SECONDS))process.destroyForcibly();}catch(InterruptedException ex){Thread.currentThread().interrupt();process.destroyForcibly();}}}
}
