package de.dennysubke.oniondrop;

import android.app.*;
import android.content.*;
import android.content.pm.ServiceInfo;
import android.graphics.Bitmap;
import android.graphics.BitmapFactory;
import android.os.*;
import de.dennysubke.oniondrop.core.*;
import java.io.*;
import java.util.concurrent.*;

/** User-started, bounded foreground session. Tor is stopped when this service ends. */
public final class DropService extends Service {
    public static final String START_SEND="de.dennysubke.oniondrop.SEND",START_RECEIVE="de.dennysubke.oniondrop.RECEIVE",STOP="de.dennysubke.oniondrop.STOP";
    private static final String CHANNEL="oniondrop-transfers";
    private static final int NOTICE=50;
    public static final long SESSION_MS=30*60*1000L;
    public static final class State {
        public final String phase,host,message,sendToken,receiveToken;
        public final int progress;public final boolean sending,receiving;public final long until;
        State(String p,String h,String m,String st,String rt,int n,boolean s,boolean r,long u){phase=p;host=h;message=m;sendToken=st;receiveToken=rt;progress=n;sending=s;receiving=r;until=u;}
        public boolean active(){return phase.equals("starting")||phase.equals("ready")||phase.equals("stopping");}
        public boolean ready(){return phase.equals("ready");}
        public String sendUrl(){return ready()&&sending?"http://"+host+"/s/"+sendToken+"/":"";}
        public String receiveUrl(){return ready()&&receiving?"http://"+host+"/r/"+receiveToken+"/":"";}
    }
    private static volatile State state=new State("idle","","","","",0,false,false,0);
    public static State state(){return state;}
    private final Handler handler=new Handler(Looper.getMainLooper());
    private final ExecutorService engine=Executors.newSingleThreadExecutor();
    private DropServer server;private TorRunner tor;private PowerManager.WakeLock wake;
    private boolean stopping;private long until;
    private final Runnable expire=()->finishSession(AppLanguage.wrap(this).getString(R.string.session_expired),false);
    @Override public void onCreate(){super.onCreate();NotificationChannel c=new NotificationChannel(CHANNEL,AppLanguage.wrap(this).getString(R.string.channel_name),NotificationManager.IMPORTANCE_LOW);c.setDescription(AppLanguage.wrap(this).getString(R.string.channel_desc));getSystemService(NotificationManager.class).createNotificationChannel(c);}
    @Override public int onStartCommand(Intent intent,int flags,int startId){
        if(intent==null){stopSelf();return START_NOT_STICKY;}
        if(STOP.equals(intent.getAction())){finishSession(AppLanguage.wrap(this).getString(R.string.session_stopped_saved),false);return START_NOT_STICKY;}
        if(stopping)return START_NOT_STICKY;
        String action=intent.getAction();if(!START_SEND.equals(action)&&!START_RECEIVE.equals(action)){stopSelf();return START_NOT_STICKY;}
        try{
            foreground(AppLanguage.wrap(this).getString(R.string.tor_connecting_message));
            if(server==null){
                until=System.currentTimeMillis()+SESSION_MS;
                byte[] logo;try(ByteArrayOutputStream out=new ByteArrayOutputStream()){Bitmap bitmap=BitmapFactory.decodeResource(getResources(),R.drawable.oniondrop_logo);if(bitmap==null)throw new IOException("OnionDrop logo missing.");bitmap.compress(Bitmap.CompressFormat.PNG,100,out);logo=out.toByteArray();}
                server=new DropServer(((DropApp)getApplication()).store(),event->handler.post(()->{if(!stopping&&state.ready())publish("ready",state.host,event,100);}),logo);
                server.start();
                wake=((PowerManager)getSystemService(POWER_SERVICE)).newWakeLock(PowerManager.PARTIAL_WAKE_LOCK,"OnionDrop:transfer");wake.acquire(SESSION_MS+15000);
                handler.postDelayed(expire,SESSION_MS);
                tor=new TorRunner(new TorRunner.Listener(){
                    @Override public void progress(int percent){handler.post(()->{if(!stopping&&(!state.ready()||percent<100))publish("starting","",percent==100?AppLanguage.wrap(this).getString(R.string.onion_publishing):AppLanguage.wrap(this).getString(R.string.tor_connecting_message),percent);});}
                    @Override public void published(String host){handler.post(()->{if(!stopping){server.setOnion(host);publish("ready",host,AppLanguage.wrap(this).getString(R.string.phone_reachable),100);}});}
                    @Override public void failed(String message){handler.post(()->finishSession(message,true));}
                });
                final TorRunner runner=tor;final int port=server.port();
                engine.execute(()->runner.run(new File(getApplicationInfo().nativeLibraryDir,"libtor.so"),new File(getFilesDir(),"tor"),android.os.Process.myPid(),port));
            }
            if(START_SEND.equals(action)){
                if(((DropApp)getApplication()).store().shared().isEmpty())throw new IOException(AppLanguage.wrap(this).getString(R.string.choose_first));server.sending.set(true);
            }
            if(START_RECEIVE.equals(action))server.receiving.set(true);
            publish(state.ready()?"ready":"starting",state.ready()?state.host:"",state.ready()?AppLanguage.wrap(this).getString(R.string.phone_reachable):AppLanguage.wrap(this).getString(R.string.tor_connecting_message),state.ready()?100:state.progress);
        }catch(Exception ex){finishSession(ex.getMessage()==null?AppLanguage.wrap(this).getString(R.string.share_start_failed):ex.getMessage(),true);}
        return START_NOT_STICKY;
    }
    private void publish(String phase,String host,String message,int progress){if(stopping)return;state=new State(phase,host,message,server.sendToken,server.receiveToken,progress,server.sending.get(),server.receiving.get(),until);if(Build.VERSION.SDK_INT<33||checkSelfPermission(android.Manifest.permission.POST_NOTIFICATIONS)==android.content.pm.PackageManager.PERMISSION_GRANTED)getSystemService(NotificationManager.class).notify(NOTICE,notification(message));}
    private Notification notification(String text){
        PendingIntent open=PendingIntent.getActivity(this,0,new Intent(this,MainActivity.class),PendingIntent.FLAG_IMMUTABLE|PendingIntent.FLAG_UPDATE_CURRENT);
        PendingIntent stop=PendingIntent.getService(this,1,new Intent(this,DropService.class).setAction(STOP),PendingIntent.FLAG_IMMUTABLE|PendingIntent.FLAG_UPDATE_CURRENT);
        return new Notification.Builder(this,CHANNEL).setSmallIcon(R.drawable.ic_notification).setContentTitle(AppLanguage.wrap(this).getString(R.string.notification_title)).setContentText(text).setContentIntent(open).setOngoing(true).setCategory(Notification.CATEGORY_SERVICE).setOnlyAlertOnce(true).addAction(new Notification.Action.Builder(null,AppLanguage.wrap(this).getString(R.string.stop),stop).build()).build();
    }
    private void foreground(String text){if(Build.VERSION.SDK_INT>=29)startForeground(NOTICE,notification(text),ServiceInfo.FOREGROUND_SERVICE_TYPE_DATA_SYNC);else startForeground(NOTICE,notification(text));}
    private void finishSession(String message,boolean error){
        if(stopping)return;stopping=true;state=new State("stopping","",AppLanguage.wrap(this).getString(R.string.tor_stopping_message),"","",0,false,false,0);handler.removeCallbacks(expire);
        if(server!=null)server.close();
        final TorRunner runner=tor;new Thread(()->{if(runner!=null)runner.close();state=new State(error?"error":"idle","",message,"","",0,false,false,0);},"oniondrop-stop").start();
        if(wake!=null&&wake.isHeld())wake.release();stopForeground(STOP_FOREGROUND_REMOVE);stopSelf();
    }
    @Override public void onTimeout(int startId,int fgsType){finishSession(AppLanguage.wrap(this).getString(R.string.background_ended),false);}
    @Override public void onDestroy(){finishSession(AppLanguage.wrap(this).getString(R.string.share_ended),false);handler.removeCallbacksAndMessages(null);engine.shutdown();super.onDestroy();}
    @Override public IBinder onBind(Intent intent){return null;}
}
