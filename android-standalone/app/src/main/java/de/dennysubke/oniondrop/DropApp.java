package de.dennysubke.oniondrop;
import android.app.Application;
import de.dennysubke.oniondrop.core.FileStore;
import java.io.IOException;

public final class DropApp extends Application {
    private FileStore store;
    @Override public void onCreate(){super.onCreate();try{store=new FileStore(getFilesDir());}catch(IOException ex){throw new IllegalStateException("OnionDrop-Speicher nicht verfügbar.",ex);}}
    public FileStore store(){return store;}
}
