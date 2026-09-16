package de.dennysubke.oniondrop.core;

import java.io.*;
import java.net.Socket;
import java.nio.charset.StandardCharsets;
import java.util.*;

/** Single-reader Tor control protocol; asynchronous events can interleave replies. */
public final class TorControl implements Closeable {
    public interface Events{void event(String value);}
    private final StringBuilder partial=new StringBuilder();
    private final Socket socket;private final BufferedReader in;private final BufferedWriter out;private final Events events;
    public TorControl(Socket socket,Events events)throws IOException{this.socket=socket;this.events=events;in=new BufferedReader(new InputStreamReader(socket.getInputStream(),StandardCharsets.US_ASCII));out=new BufferedWriter(new OutputStreamWriter(socket.getOutputStream(),StandardCharsets.US_ASCII));}
    public List<String> command(String command)throws IOException{
        if(command.contains("\r")||command.contains("\n"))throw new IOException("Ungültiger Tor-Befehl.");out.write(command+"\r\n");out.flush();List<String> result=new ArrayList<>();
        while(true){String line=readLine();if(line.startsWith("650")){event(line);continue;}if(!line.startsWith("250")||line.length()<4)throw new IOException("Tor konnte den Befehl nicht ausführen.");result.add(line.substring(4));if(line.charAt(3)=='+'){String value;while(!(value=readLine()).equals(".")){if(result.size()>4096)throw new IOException("Tor-Antwort zu groß.");result.add(value.startsWith("..")?value.substring(1):value);}}else if(line.charAt(3)==' ')return result;}
    }
    public void nextEvent()throws IOException{event(readLine());}
    private void event(String line)throws IOException{events.event(line);if(line.length()>3&&line.charAt(3)=='+'){int lines=0;while(!readLine().equals("."))if(++lines>4096)throw new IOException("Tor-Ereignis zu groß.");}}
    private String readLine()throws IOException{
        while(true){int ch=in.read();if(ch<0)throw new EOFException("Tor wurde beendet.");
            if(ch=='\n'){String line=partial.toString();partial.setLength(0);return line.endsWith("\r")?line.substring(0,line.length()-1):line;}
            if(partial.length()>=65536)throw new IOException("Tor-Antwort zu lang.");partial.append((char)ch);
        }
    }
    @Override public void close()throws IOException{socket.close();}
}
