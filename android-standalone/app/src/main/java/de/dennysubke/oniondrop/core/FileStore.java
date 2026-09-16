package de.dennysubke.oniondrop.core;

import java.io.*;
import java.nio.file.*;
import java.util.*;

/** Private app storage. Untrusted display names never become filesystem paths. */
public final class FileStore implements DropServer.Repository {
    public static final long QUOTA=1024L*1024*1024;
    private final File sharedDir,receivedDir;
    private long sharedReserved,receivedReserved;
    private int sharedPending,receivedPending;
    public FileStore(File root)throws IOException{
        sharedDir=new File(root,"shared");receivedDir=new File(root,"received");
        for(File dir:new File[]{sharedDir,receivedDir}){
            if(!dir.isDirectory()&&!dir.mkdirs())throw new IOException("Speicherverzeichnis nicht verfügbar.");
            File[] files=dir.listFiles();if(files!=null)for(File f:files){
                if(f.getName().endsWith(".part")||f.getName().endsWith(".pending"))f.delete();
                if(f.getName().endsWith(".bin")&&!new File(dir,f.getName().replace(".bin",".meta")).isFile())f.delete();
            }
        }
    }
    @Override public synchronized List<DropFile> shared(){return list(sharedDir);}
    public synchronized List<DropFile> received(){return list(receivedDir);}
    private List<DropFile> list(File dir){
        List<DropFile> items=new ArrayList<>();File[] metas=dir.listFiles((d,n)->n.matches("[a-f0-9]{32}\\.meta"));if(metas==null)return items;
        for(File meta:metas){try(InputStream in=new FileInputStream(meta)){
            Properties p=new Properties();p.load(in);String id=meta.getName().substring(0,32);File file=new File(dir,id+".bin");if(!file.isFile())continue;
            items.add(new DropFile(id,DropSecurity.filename(p.getProperty("name","Datei")),p.getProperty("mime","application/octet-stream"),file,file.length(),Long.parseLong(p.getProperty("created","0"))));
        }catch(Exception ignored){}}
        items.sort((a,b)->Long.compare(b.createdAt,a.createdAt));return items;
    }
    private long used(File dir){long n=0;for(DropFile f:list(dir))n+=f.size;return n;}
    @Override public DropFile receive(String name,long length,InputStream source)throws IOException{return write(false,name,"application/octet-stream",length,source);}
    public DropFile importFile(String name,String mime,long length,InputStream source)throws IOException{return write(true,name,mime,length,source);}
    private DropFile write(boolean shared,String name,String mime,long length,InputStream source)throws IOException{
        if(length>DropServer.MAX_FILE||length< -1)throw new IOException("Maximal 250 MiB pro Datei.");
        File dir=shared?sharedDir:receivedDir;long reservation=length<0?DropServer.MAX_FILE:length;
        synchronized(this){
            long reserved=shared?sharedReserved:receivedReserved;int pending=shared?sharedPending:receivedPending;
            if(used(dir)+reserved+reservation>QUOTA||list(dir).size()+pending>=100)throw new IOException("Speicherlimit erreicht (1 GiB / 100 Dateien pro Bereich).");
            if(shared){sharedReserved+=reservation;sharedPending++;}else{receivedReserved+=reservation;receivedPending++;}
        }
        String id=UUID.randomUUID().toString().replace("-","");File part=new File(dir,id+".part"),file=new File(dir,id+".bin"),metaPart=new File(dir,id+".pending"),meta=new File(dir,id+".meta");boolean committed=false;long total=0;
        try{
            try(FileOutputStream out=new FileOutputStream(part)){
                byte[] b=new byte[32768];
                while(length<0||total<length){int max=length<0?b.length:(int)Math.min(b.length,length-total);int n=source.read(b,0,max);if(n<0){if(length>=0&&total<length)throw new EOFException("Übertragung abgebrochen.");break;}total+=n;if(total>DropServer.MAX_FILE)throw new IOException("Datei zu groß.");out.write(b,0,n);}
                if(shared&&length>=0&&source.read()!=-1)throw new IOException("Dateigröße hat sich geändert. Bitte erneut auswählen.");
                out.getFD().sync();
            }
            long time=System.currentTimeMillis();Properties p=new Properties();p.setProperty("name",DropSecurity.filename(name));p.setProperty("mime",mime==null?"application/octet-stream":mime);p.setProperty("created",Long.toString(time));
            try(FileOutputStream out=new FileOutputStream(metaPart)){p.store(out,"OnionDrop private file metadata");out.getFD().sync();}
            synchronized(this){Files.move(part.toPath(),file.toPath(),StandardCopyOption.ATOMIC_MOVE);Files.move(metaPart.toPath(),meta.toPath(),StandardCopyOption.ATOMIC_MOVE);committed=true;}
            return new DropFile(id,p.getProperty("name"),p.getProperty("mime"),file,total,time);
        }finally{
            synchronized(this){if(shared){sharedReserved-=reservation;sharedPending--;}else{receivedReserved-=reservation;receivedPending--;}}
            if(!committed){part.delete();file.delete();metaPart.delete();meta.delete();}
        }
    }
    public synchronized void delete(boolean shared,String id)throws IOException{
        if(!id.matches("[a-f0-9]{32}"))throw new IOException("Ungültige Datei.");File dir=shared?sharedDir:receivedDir;
        Files.deleteIfExists(new File(dir,id+".bin").toPath());Files.deleteIfExists(new File(dir,id+".meta").toPath());
    }
}
