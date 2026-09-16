package de.dennysubke.oniondrop;

import android.Manifest;
import android.app.*;
import android.content.*;
import android.content.pm.PackageManager;
import android.database.Cursor;
import android.graphics.*;
import android.graphics.drawable.*;
import android.net.Uri;
import android.os.*;
import android.provider.OpenableColumns;
import android.view.*;
import android.widget.*;
import com.google.zxing.*;
import com.google.zxing.common.BitMatrix;
import de.dennysubke.oniondrop.core.*;
import java.io.*;
import java.security.MessageDigest;
import java.util.*;
import java.util.concurrent.*;

/** Native, local-first Android UI. All displayed transfer state comes from the foreground service. */
public final class MainActivity extends Activity {
    private static final int BG=0xff100c19,CARD=0xff1c1527,LINE=0xff352640,WHITE=0xfff6efff,MUTED=0xffb1a3c1,PURPLE=0xffc59bff,GREEN=0xff90d8bf;
    private static final int PICK=11,EXPORT=12,NOTIFICATION_PERMISSION=13;
    private final Handler handler=new Handler(Looper.getMainLooper());
    private final ExecutorService io=Executors.newSingleThreadExecutor();
    private LinearLayout root,content;private ScrollView scroll;private TextView countdown;private ProgressBar progress;
    private FileStore store;private int tab;private boolean visible,busy;private String lastSignature="",pendingStart;private DropFile exportFile;
    private final Runnable tick=new Runnable(){@Override public void run(){if(!visible)return;DropService.State s=DropService.state();String signature=s.phase+":"+s.progress+":"+s.sending+":"+s.receiving+":"+s.message+":"+store.shared().size()+":"+store.received().size();if(!signature.equals(lastSignature)&&!busy){lastSignature=signature;render(false);}if(countdown!=null&&s.active())countdown.setText("Automatisches Ende in "+remaining(s.until));handler.postDelayed(this,1000);}};
    interface Work<T>{T run()throws Exception;}interface Done<T>{void accept(T value)throws Exception;}
    @Override public void onCreate(Bundle saved){super.onCreate(saved);store=((DropApp)getApplication()).store();if(saved!=null)tab=saved.getInt("tab",0);getWindow().setStatusBarColor(BG);getWindow().setNavigationBarColor(BG);render(true);if(saved==null)handleShare(getIntent());}
    @Override protected void onSaveInstanceState(Bundle out){super.onSaveInstanceState(out);out.putInt("tab",tab);}
    @Override protected void onNewIntent(Intent intent){super.onNewIntent(intent);setIntent(intent);handleShare(intent);}
    @Override protected void onResume(){super.onResume();visible=true;handler.post(tick);}
    @Override protected void onPause(){visible=false;handler.removeCallbacks(tick);super.onPause();}
    @Override protected void onDestroy(){handler.removeCallbacksAndMessages(null);io.shutdown();super.onDestroy();}
    @Override public void onBackPressed(){if(tab!=0){tab=0;render(true);}else super.onBackPressed();}
    private int dp(float n){return Math.round(n*getResources().getDisplayMetrics().density);}
    private LinearLayout col(){LinearLayout l=new LinearLayout(this);l.setOrientation(LinearLayout.VERTICAL);return l;}
    private LinearLayout row(){LinearLayout l=new LinearLayout(this);l.setGravity(Gravity.CENTER_VERTICAL);return l;}
    private GradientDrawable background(int color,int radius){GradientDrawable d=new GradientDrawable();d.setColor(color);d.setCornerRadius(dp(radius));d.setStroke(dp(1),LINE);return d;}
    private GradientDrawable gradient(int a,int b,int radius){GradientDrawable d=new GradientDrawable(GradientDrawable.Orientation.TL_BR,new int[]{a,b});d.setCornerRadius(dp(radius));d.setStroke(dp(1),LINE);return d;}
    private TextView text(String value,int size,int color,boolean strong){TextView t=new TextView(this);t.setText(value);t.setTextSize(size);t.setTextColor(color);t.setLineSpacing(dp(3),1);if(strong)t.setTypeface(Typeface.create("sans-serif-medium",Typeface.NORMAL));return t;}
    private void label(LinearLayout p,String value,int size,int color,boolean strong){p.addView(text(value,size,color,strong));}
    private void gap(LinearLayout p,int size){p.addView(new View(this),new LinearLayout.LayoutParams(1,dp(size)));}
    private TextView center(LinearLayout p,String value,int size,int color,boolean strong){TextView t=text(value,size,color,strong);t.setGravity(Gravity.CENTER);p.addView(t,new LinearLayout.LayoutParams(-1,-2));return t;}
    private LinearLayout card(LinearLayout parent){LinearLayout box=col();box.setPadding(dp(18),dp(18),dp(18),dp(18));box.setBackground(background(CARD,22));LinearLayout.LayoutParams lp=new LinearLayout.LayoutParams(-1,-2);lp.bottomMargin=dp(14);parent.addView(box,lp);return box;}
    private View button(String title,String icon,boolean primary,Runnable action){LinearLayout b=row();b.setGravity(Gravity.CENTER);b.setMinimumHeight(dp(52));b.setPadding(dp(12),dp(12),dp(12),dp(12));b.setBackground(primary?gradient(0xffcfafff,0xffaf78f0,16):background(CARD,16));if(icon!=null){b.addView(new Icon(icon,primary?BG:PURPLE),new LinearLayout.LayoutParams(dp(20),dp(20)));}TextView t=text((icon==null?"":"  ")+title,14,primary?BG:WHITE,true);b.addView(t);b.setClickable(true);b.setFocusable(true);b.setContentDescription(title);b.setForeground(getDrawable(android.R.drawable.list_selector_background));b.setOnClickListener(v->{if(!busy)action.run();});return b;}
    private void full(LinearLayout p,String title,String icon,boolean primary,Runnable action){p.addView(button(title,icon,primary,action),new LinearLayout.LayoutParams(-1,-2));}
    private void base(){
        root=col();root.setBackgroundColor(BG);root.setOnApplyWindowInsetsListener((v,w)->{if(Build.VERSION.SDK_INT>=30){Insets i=w.getInsets(WindowInsets.Type.systemBars()|WindowInsets.Type.ime());v.setPadding(i.left,i.top,i.right,i.bottom);}else v.setPadding(w.getSystemWindowInsetLeft(),w.getSystemWindowInsetTop(),w.getSystemWindowInsetRight(),w.getSystemWindowInsetBottom());return w;});setContentView(root);root.requestApplyInsets();
        LinearLayout header=row();header.setPadding(dp(21),dp(15),dp(18),dp(12));ImageView logo=new ImageView(this);logo.setImageResource(R.drawable.oniondrop_logo);logo.setContentDescription("OnionDrop Original-Logo");header.addView(logo,new LinearLayout.LayoutParams(dp(44),dp(44)));
        LinearLayout brand=col();brand.setPadding(dp(11),0,0,0);label(brand,"OnionDrop",21,WHITE,true);TextView sub=text("PRIVATE FILE SHARING",9,MUTED,true);sub.setLetterSpacing(.13f);brand.addView(sub);header.addView(brand,new LinearLayout.LayoutParams(0,-2,1));
        View info=button("","info",false,this::about);info.setContentDescription("Über OnionDrop");header.addView(info,new LinearLayout.LayoutParams(dp(48),dp(48)));root.addView(header);
        progress=new ProgressBar(this,null,android.R.attr.progressBarStyleHorizontal);progress.setIndeterminate(true);progress.setVisibility(busy?View.VISIBLE:View.INVISIBLE);root.addView(progress,new LinearLayout.LayoutParams(-1,dp(2)));
        scroll=new ScrollView(this);scroll.setFillViewport(true);content=col();content.setPadding(dp(22),dp(13),dp(22),dp(20));scroll.addView(content);root.addView(scroll,new LinearLayout.LayoutParams(-1,0,1));countdown=null;
    }
    private void render(boolean top){int y=top||scroll==null?0:scroll.getScrollY();base();if(tab==0)home();else if(tab==1)send();else receive();navigation();scroll.post(()->scroll.scrollTo(0,y));}
    private void home(){
        DropService.State s=DropService.state();
        LinearLayout status=row();status.setGravity(Gravity.CENTER);TextView badge=text("●  "+(s.ready()?"TOR VERBUNDEN":s.phase.equals("stopping")?"TOR WIRD BEENDET":s.active()?"TOR VERBINDET":"BEREIT, WENN DU ES BIST"),10,s.ready()?GREEN:PURPLE,true);badge.setLetterSpacing(.08f);badge.setPadding(dp(14),dp(8),dp(14),dp(8));badge.setBackground(background(0xff23192e,30));status.addView(badge);content.addView(status);gap(content,17);
        LinearLayout hero=card(content);hero.setBackground(gradient(0xff2b1d3c,0xff191223,28));hero.setPadding(dp(22),dp(7),dp(22),dp(23));
        hero.addView(new BrandHalo(s.active()?s.progress:-1,s.ready()),new LinearLayout.LayoutParams(-1,dp(158)));
        center(hero,s.ready()?"Dein Drop ist bereit.":"Dein Drop.\nDeine Kontrolle.",27,WHITE,true);gap(hero,10);
        center(hero,s.active()?s.message:"Dateien direkt teilen und empfangen.\nOhne Konto. Ohne Cloud.",13,MUTED,false);
        if(s.active()){gap(hero,17);countdown=center(hero,"Automatisches Ende in "+remaining(s.until),11,PURPLE,true);gap(hero,14);full(hero,"Freigaben beenden","stop",false,this::stop);}
        if(s.phase.equals("error")){gap(hero,12);center(hero,s.message,12,0xffffb7bc,false);}
        gap(content,5);actionCard("Dateien senden","Von deinem Handy. Direkt.","send",PURPLE,()->{tab=1;render(true);});actionCard("Dateien empfangen","Dein privater Eingang.","receive",GREEN,()->{tab=2;render(true);});
        gap(content,7);LinearLayout foot=row();foot.setGravity(Gravity.CENTER);foot.addView(new Icon("shield",MUTED),new LinearLayout.LayoutParams(dp(16),dp(16)));foot.addView(text("  Direkt über Tor · alles auf deinem Gerät",11,MUTED,false));content.addView(foot);
    }
    private void actionCard(String title,String subtitle,String icon,int color,Runnable action){
        LinearLayout box=card(content);box.setPadding(dp(16),dp(18),dp(16),dp(18));LinearLayout r=row();FrameLayout tile=new FrameLayout(this);tile.setBackground(background(color==GREEN?0xff19312e:0xff362044,15));Icon glyph=new Icon(icon,color);FrameLayout.LayoutParams ip=new FrameLayout.LayoutParams(dp(24),dp(24),Gravity.CENTER);tile.addView(glyph,ip);r.addView(tile,new LinearLayout.LayoutParams(dp(48),dp(48)));LinearLayout words=col();words.setPadding(dp(14),0,dp(7),0);label(words,title,17,WHITE,true);gap(words,4);label(words,subtitle,12,MUTED,false);r.addView(words,new LinearLayout.LayoutParams(0,-2,1));r.addView(new Icon("chevron",MUTED),new LinearLayout.LayoutParams(dp(18),dp(18)));box.addView(r);box.setClickable(true);box.setFocusable(true);box.setContentDescription(title+". "+subtitle);box.setForeground(getDrawable(android.R.drawable.list_selector_background));box.setOnClickListener(v->{if(!busy)action.run();});
    }
    private void title(String eyebrow,String title,String subtitle){TextView e=text(eyebrow,10,PURPLE,true);e.setLetterSpacing(.12f);content.addView(e);gap(content,9);label(content,title,27,WHITE,true);gap(content,9);label(content,subtitle,13,MUTED,false);gap(content,23);}
    private void send(){
        DropService.State s=DropService.state();List<DropFile> files=store.shared();
        title("SENDEN","Deine Dateien.\nDein Link.","Wähle aus, was du teilen möchtest. Nur diese Dateien sind über deinen Link erreichbar.");
        if(s.sending){sessionCard(true);}else{
            LinearLayout select=card(content);GradientDrawable border=background(0xff20172c,22);border.setStroke(dp(1),0xff705084,dp(5),dp(5));select.setBackground(border);gap(select,4);center(select,files.isEmpty()?"Was möchtest du teilen?":"Noch etwas hinzufügen?",17,WHITE,true);gap(select,8);center(select,"Bis zu 250 MiB je Datei",12,MUTED,false);gap(select,18);full(select,"Dateien auswählen","plus",true,this::pick);
            if(!files.isEmpty()){full(content,"Freigabe starten","send",true,()->start(DropService.START_SEND));gap(content,21);}
        }
        section(files.size()+" DATEIEN AUSGEWÄHLT");
        if(files.isEmpty())empty("Noch nichts ausgewählt.","Deine Dateien bleiben privat, bis du die Freigabe startest.","folder");
        for(DropFile f:files)fileCard(f,true);
        if(!s.sending&&!files.isEmpty()){gap(content,6);label(content,"Die App erstellt eine lokale Kopie. Du kannst die Auswahl entfernen, ohne das Original zu löschen.",11,MUTED,false);}
    }
    private void receive(){
        DropService.State s=DropService.state();List<DropFile> files=store.received();
        title("EMPFANGEN","Dein privater Eingang.","Teile deinen Empfangslink. Andere können Dateien direkt auf deinem Handy ablegen.");
        if(s.receiving)sessionCard(false);else{full(content,"Empfang starten","receive",true,()->start(DropService.START_RECEIVE));gap(content,17);label(content,"Dein Link öffnet sich im Tor Browser. Besuchern werden keine empfangenen Dateien angezeigt.",12,MUTED,false);gap(content,19);}
        section(files.size()+" DATEIEN EMPFANGEN");if(files.isEmpty())empty("Hier kommt dein nächster Drop an.","Empfangene Dateien werden ausschließlich in der App gespeichert.","receive");for(DropFile f:files)fileCard(f,false);
    }
    private void sessionCard(boolean send){
        DropService.State s=DropService.state();LinearLayout box=card(content);box.setBackground(gradient(0xff2b1d3c,0xff1c1527,22));label(box,s.ready()?"●  Dein Link ist bereit":"●  "+s.progress+" % · Tor wird verbunden",13,s.ready()?GREEN:PURPLE,true);gap(box,13);
        String url=send?s.sendUrl():s.receiveUrl();
        if(!url.isEmpty()){
            TextView address=text(url,12,WHITE,false);address.setTypeface(Typeface.MONOSPACE);address.setMaxLines(4);address.setTextIsSelectable(true);address.setPadding(dp(12),dp(12),dp(12),dp(12));address.setBackground(background(BG,12));box.addView(address);gap(box,13);
            LinearLayout actions=row();String[] labels={"Kopieren","Teilen","QR"};String[] icons={"copy","share","qr"};for(int i=0;i<3;i++){final int action=i;LinearLayout.LayoutParams lp=new LinearLayout.LayoutParams(0,dp(49),1);if(i<2)lp.rightMargin=dp(6);actions.addView(button(labels[i],null,false,()->{if(action==0)copy(url);else if(action==1)share(url);else qr(url);}),lp);}box.addView(actions);
            gap(box,12);label(box,"Jeder mit diesem Link kann "+(send?"die ausgewählten Dateien abrufen.":"Dateien abgeben.")+" Gib ihn nur an die vorgesehenen Personen weiter.",11,MUTED,false);
        }else{label(box,s.message,13,MUTED,false);gap(box,12);ProgressBar p=new ProgressBar(this,null,android.R.attr.progressBarStyleHorizontal);p.setMax(100);p.setProgress(s.progress);box.addView(p,new LinearLayout.LayoutParams(-1,dp(5)));}
        gap(box,15);countdown=text("Automatisches Ende in "+remaining(s.until),11,PURPLE,true);box.addView(countdown);gap(box,14);full(box,"Alle Freigaben beenden","stop",false,this::stop);
    }
    private void section(String value){label(content,value,10,MUTED,true);gap(content,13);}
    private void empty(String title,String subtitle,String icon){LinearLayout box=card(content);Icon i=new Icon(icon,0xff786888);LinearLayout.LayoutParams p=new LinearLayout.LayoutParams(dp(34),dp(34));p.gravity=Gravity.CENTER_HORIZONTAL;box.addView(i,p);gap(box,14);center(box,title,16,WHITE,true);gap(box,7);center(box,subtitle,12,MUTED,false);}
    private void fileCard(DropFile file,boolean shared){
        LinearLayout card=card(content);LinearLayout r=row();FrameLayout tile=new FrameLayout(this);tile.setBackground(background(0xff30203f,13));String ext=file.name.contains(".")?file.name.substring(file.name.lastIndexOf('.')+1).toUpperCase(Locale.ROOT):"FILE";if(ext.length()>4)ext="FILE";TextView e=text(ext,10,PURPLE,true);e.setGravity(Gravity.CENTER);tile.addView(e,new FrameLayout.LayoutParams(-1,-1));r.addView(tile,new LinearLayout.LayoutParams(dp(44),dp(50)));
        LinearLayout words=col();words.setPadding(dp(12),0,dp(6),0);label(words,file.name,15,WHITE,true);gap(words,5);label(words,size(file.size),12,MUTED,false);r.addView(words,new LinearLayout.LayoutParams(0,-2,1));View more=button("","more",false,()->fileMenu(file,shared));more.setContentDescription("Aktionen für "+file.name);r.addView(more,new LinearLayout.LayoutParams(dp(40),dp(48)));card.addView(r);
    }
    private void navigation(){LinearLayout nav=row();nav.setPadding(dp(14),dp(10),dp(14),dp(15));String[] names={"Übersicht","Senden","Empfangen"},icons={"home","send","receive"};for(int i=0;i<3;i++){final int dest=i;LinearLayout item=col();item.setGravity(Gravity.CENTER);item.setPadding(dp(4),dp(10),dp(4),dp(10));if(tab==i)item.setBackground(background(0xff2d1d3d,17));Icon icon=new Icon(icons[i],tab==i?PURPLE:MUTED);item.addView(icon,new LinearLayout.LayoutParams(dp(23),dp(23)));gap(item,5);item.addView(text(names[i],10,tab==i?PURPLE:MUTED,tab==i));item.setClickable(true);item.setFocusable(true);item.setContentDescription(names[i]);item.setOnClickListener(v->{if(!busy){tab=dest;render(true);}});LinearLayout.LayoutParams p=new LinearLayout.LayoutParams(0,dp(70),1);p.setMargins(dp(3),0,dp(3),0);nav.addView(item,p);}root.addView(nav);}
    private void pick(){if(DropService.state().sending){toast("Bitte die Freigabe zuerst beenden.");return;}Intent i=new Intent(Intent.ACTION_OPEN_DOCUMENT).addCategory(Intent.CATEGORY_OPENABLE).setType("*/*").putExtra(Intent.EXTRA_ALLOW_MULTIPLE,true);startActivityForResult(i,PICK);}
    private void handleShare(Intent intent){if(intent==null)return;String action=intent.getAction();ArrayList<Uri> list=new ArrayList<>();if(Intent.ACTION_SEND.equals(action)){Uri uri=intent.getParcelableExtra(Intent.EXTRA_STREAM);if(uri!=null)list.add(uri);}else if(Intent.ACTION_SEND_MULTIPLE.equals(action)){ArrayList<Uri> items=intent.getParcelableArrayListExtra(Intent.EXTRA_STREAM);if(items!=null)list.addAll(items);}if(!list.isEmpty()){tab=1;render(true);new AlertDialog.Builder(this).setTitle("Dateien in OnionDrop übernehmen?").setMessage(list.size()+" Datei(en) werden lokal kopiert. Die Freigabe startest du anschließend selbst.").setPositiveButton("Übernehmen",(d,w)->importFiles(list)).setNegativeButton("Abbrechen",null).show();}}
    @Override protected void onActivityResult(int code,int result,Intent data){super.onActivityResult(code,result,data);if(result!=RESULT_OK||data==null)return;if(code==PICK){ArrayList<Uri> list=new ArrayList<>();if(data.getClipData()!=null){for(int n=0;n<data.getClipData().getItemCount();n++)list.add(data.getClipData().getItemAt(n).getUri());}else if(data.getData()!=null)list.add(data.getData());importFiles(list);}else if(code==EXPORT&&data.getData()!=null){if(exportFile==null){toast("Bitte die Datei erneut auswählen.");return;}DropFile file=exportFile;exportFile=null;Uri target=data.getData();work(()->{try(InputStream in=new FileInputStream(file.file);OutputStream out=getContentResolver().openOutputStream(target,"w")){if(out==null)throw new IOException("Speicherort nicht verfügbar.");byte[] b=new byte[32768];int n;while((n=in.read(b))!=-1)out.write(b,0,n);}catch(Exception ex){try{android.provider.DocumentsContract.deleteDocument(getContentResolver(),target);}catch(Exception ignored){}throw ex;}return true;},v->toast("Datei gespeichert."));}}
    private void importFiles(List<Uri> uris){if(DropService.state().sending){toast("Bitte die Freigabe zuerst beenden.");return;}if(uris.size()>20){toast("Bitte höchstens 20 Dateien auf einmal auswählen.");return;}work(()->{int imported=0;for(Uri uri:uris){try{if(!"content".equals(uri.getScheme()))throw new IOException("Bitte Dateien über die Android-Dateiauswahl öffnen.");String name="Datei";long length=-1;try(Cursor c=getContentResolver().query(uri,new String[]{OpenableColumns.DISPLAY_NAME,OpenableColumns.SIZE},null,null,null)){if(c!=null&&c.moveToFirst()){name=c.getString(0);if(!c.isNull(1))length=c.getLong(1);}}try(InputStream in=getContentResolver().openInputStream(uri)){if(in==null)throw new IOException("Datei nicht lesbar.");store.importFile(name,getContentResolver().getType(uri),length,in);}imported++;}catch(Exception ex){throw new IOException(imported+" Datei(en) übernommen. "+ex.getMessage(),ex);}}return imported;},n->{tab=1;render(false);toast(n+" Datei(en) hinzugefügt.");});}
    private void fileMenu(DropFile file,boolean shared){String[] options=shared?new String[]{"SHA-256 anzeigen","Auswahl entfernen"}:new String[]{"Auf dem Gerät speichern","SHA-256 anzeigen","Datei löschen"};new AlertDialog.Builder(this).setTitle(file.name).setItems(options,(d,index)->{int action=shared?index+1:index;if(action==0){exportFile=file;Intent i=new Intent(Intent.ACTION_CREATE_DOCUMENT).addCategory(Intent.CATEGORY_OPENABLE).setType("application/octet-stream").putExtra(Intent.EXTRA_TITLE,file.name);startActivityForResult(i,EXPORT);}if(action==1)checksum(file);if(action==2){if(shared&&DropService.state().sending){toast("Bitte die Freigabe zuerst beenden.");return;}new AlertDialog.Builder(this).setTitle(shared?"Lokale Auswahl entfernen?":"Datei aus OnionDrop löschen?").setMessage(shared?"Das Original bleibt erhalten.":"Speichere bei Bedarf vorher eine Kopie außerhalb der App.").setNegativeButton("Abbrechen",null).setPositiveButton("Entfernen",(a,b)->work(()->{store.delete(shared,file.id);return true;},v->render(false))).show();}}).show();}
    private void checksum(DropFile file){work(()->{MessageDigest hash=MessageDigest.getInstance("SHA-256");try(InputStream in=new FileInputStream(file.file)){byte[] b=new byte[32768];int n;while((n=in.read(b))!=-1)hash.update(b,0,n);}return DropSecurity.hex(hash.digest());},hash->new AlertDialog.Builder(this).setTitle("SHA-256").setMessage(hash).setPositiveButton("Kopieren",(d,w)->copy(hash)).setNegativeButton("Schließen",null).show());}
    private void start(String action){if(DropService.state().phase.equals("stopping")){toast("Tor wird noch beendet. Bitte kurz warten.");return;}if(Build.VERSION.SDK_INT>=33&&checkSelfPermission(Manifest.permission.POST_NOTIFICATIONS)!=PackageManager.PERMISSION_GRANTED){pendingStart=action;requestPermissions(new String[]{Manifest.permission.POST_NOTIFICATIONS},NOTIFICATION_PERMISSION);}else launch(action);}
    @Override public void onRequestPermissionsResult(int request,String[] permissions,int[] results){super.onRequestPermissionsResult(request,permissions,results);if(request==NOTIFICATION_PERMISSION&&pendingStart!=null){String action=pendingStart;pendingStart=null;if(results.length==0||results[0]!=PackageManager.PERMISSION_GRANTED)toast("Die Sitzung erscheint in Androids aktiven Apps. Du kannst sie jederzeit in OnionDrop beenden.");launch(action);}}
    private void launch(String action){try{startForegroundService(new Intent(this,DropService.class).setAction(action));toast("Tor wird gestartet …");}catch(Exception ex){error(ex);}handler.postDelayed(()->render(false),250);}
    private void stop(){new AlertDialog.Builder(this).setTitle("Alle Freigaben beenden?").setMessage("Aktive Übertragungen werden abgebrochen und beide Links ungültig. Gespeicherte Dateien bleiben erhalten.").setNegativeButton("Weiterlaufen lassen",null).setPositiveButton("Beenden",(d,w)->{startService(new Intent(this,DropService.class).setAction(DropService.STOP));handler.postDelayed(()->render(false),250);}).show();}
    private void copy(String value){ClipData clip=ClipData.newPlainText("OnionDrop",value);if(Build.VERSION.SDK_INT>=33){PersistableBundle extras=new PersistableBundle();extras.putBoolean(ClipDescription.EXTRA_IS_SENSITIVE,true);clip.getDescription().setExtras(extras);}((ClipboardManager)getSystemService(CLIPBOARD_SERVICE)).setPrimaryClip(clip);toast("Kopiert.");}
    private void share(String value){startActivity(Intent.createChooser(new Intent(Intent.ACTION_SEND).setType("text/plain").putExtra(Intent.EXTRA_TEXT,value),"Privaten OnionDrop-Link teilen"));}
    private void qr(String value){work(()->{Map<EncodeHintType,Object> hints=new EnumMap<>(EncodeHintType.class);hints.put(EncodeHintType.MARGIN,3);BitMatrix matrix=new MultiFormatWriter().encode(value,BarcodeFormat.QR_CODE,640,640,hints);Bitmap bitmap=Bitmap.createBitmap(640,640,Bitmap.Config.ARGB_8888);int[] pixels=new int[640*640];for(int y=0;y<640;y++)for(int x=0;x<640;x++)pixels[y*640+x]=matrix.get(x,y)?Color.BLACK:Color.WHITE;bitmap.setPixels(pixels,0,640,0,0,640,640);return bitmap;},bitmap->{ImageView v=new ImageView(this);v.setImageBitmap(bitmap);v.setAdjustViewBounds(true);v.setPadding(dp(20),dp(20),dp(20),dp(20));v.setBackgroundColor(Color.WHITE);new AlertDialog.Builder(this).setTitle("Dein privater Link").setView(v).setPositiveButton("Schließen",null).show();});}
    private void about(){new AlertDialog.Builder(this).setTitle("OnionDrop · eigenständig").setMessage("Version 0.2.0 Alpha\n\nTor und Dateiübertragungen laufen auf deinem Handy. Ein Server, Umbrel oder Orbot wird nicht benötigt.\n\nEine Sitzung endet nach 30 Minuten. Android oder ein Verbindungsabbruch können sie früher beenden. Der Empfangslink benötigt JavaScript im Tor Browser.\n\n250 MiB je Datei · 1 GiB und 100 Dateien je Bereich. Inhalte werden im privaten App-Speicher abgelegt; beim Deinstallieren werden sie gelöscht.\n\nOriginal-Logo: Denny’s OnionDrop\nTor: The Tor Project / Guardian Project (0.4.9.12)\nQR-Codes: ZXing (Apache-2.0)\nOnionDrop: GPL-3.0-or-later\n\nDiese Alpha ist noch nicht auf einem Android-Gerät mit einer echten Tor-Übertragung validiert.").setPositiveButton("Verstanden",null).show();}
    private void toast(String msg){Toast.makeText(this,msg,Toast.LENGTH_LONG).show();}
    private void error(Exception ex){if(isDestroyed()||isFinishing())return;new AlertDialog.Builder(this).setTitle("Aktion nicht abgeschlossen").setMessage(ex.getMessage()==null?"Bitte erneut versuchen.":ex.getMessage()).setPositiveButton("OK",null).show();}
    private <T> void work(Work<T> job,Done<T> done){if(busy)return;busy=true;if(progress!=null)progress.setVisibility(View.VISIBLE);io.execute(()->{try{T result=job.run();handler.post(()->{if(isDestroyed()||isFinishing())return;busy=false;progress.setVisibility(View.INVISIBLE);try{done.accept(result);}catch(Exception ex){error(ex);}});}catch(Exception ex){handler.post(()->{if(isDestroyed()||isFinishing())return;busy=false;render(false);error(ex);});}});}
    private String size(long bytes){if(bytes<1024)return bytes+" B";if(bytes<1048576)return String.format(Locale.GERMANY,"%.0f KiB",bytes/1024.0);if(bytes<1073741824)return String.format(Locale.GERMANY,"%.1f MiB",bytes/1048576.0);return String.format(Locale.GERMANY,"%.2f GiB",bytes/1073741824.0);}
    private String remaining(long end){long seconds=Math.max(0,(end-System.currentTimeMillis())/1000);return String.format(Locale.ROOT,"%02d:%02d",seconds/60,seconds%60);}
    private final class BrandHalo extends View {
        final int percent;final boolean ready;final Paint p=new Paint(Paint.ANTI_ALIAS_FLAG);final Bitmap logo=BitmapFactory.decodeResource(getResources(),R.drawable.oniondrop_logo);
        BrandHalo(int percent,boolean ready){super(MainActivity.this);this.percent=percent;this.ready=ready;setContentDescription(ready?"Tor verbunden":percent>=0?"Tor verbindet: "+percent+" Prozent":"OnionDrop");}
        @Override protected void onDraw(Canvas c){float x=getWidth()/2f,y=getHeight()/2f,r=dp(68);p.setShader(new RadialGradient(x,y,r,new int[]{0x505e3286,0x00391d50},null,Shader.TileMode.CLAMP));p.setStyle(Paint.Style.FILL);c.drawCircle(x,y,r,p);p.setShader(null);p.setStyle(Paint.Style.STROKE);p.setStrokeWidth(dp(1));p.setColor(0xff49305e);c.drawCircle(x,y,dp(60),p);p.setColor(0xff382449);c.drawCircle(x,y,dp(70),p);if(percent>=0){p.setColor(ready?GREEN:PURPLE);p.setStrokeWidth(dp(2));p.setStrokeCap(Paint.Cap.ROUND);c.drawArc(x-dp(60),y-dp(60),x+dp(60),y+dp(60),-90,Math.max(8,percent*3.6f),false,p);}p.setStyle(Paint.Style.FILL);c.drawBitmap(logo,null,new RectF(x-dp(44),y-dp(44),x+dp(44),y+dp(44)),p);}
    }
    private final class Icon extends View {
        final String name;final Paint p=new Paint(Paint.ANTI_ALIAS_FLAG);
        Icon(String name,int color){super(MainActivity.this);this.name=name;p.setColor(color);p.setStyle(Paint.Style.STROKE);p.setStrokeWidth(1.7f);p.setStrokeCap(Paint.Cap.ROUND);p.setStrokeJoin(Paint.Join.ROUND);setImportantForAccessibility(IMPORTANT_FOR_ACCESSIBILITY_NO);}
        void line(Canvas c,float a,float b,float d,float e){c.drawLine(a,b,d,e,p);}
        @Override protected void onDraw(Canvas c){c.save();c.scale(getWidth()/24f,getHeight()/24f);switch(name){
            case "send":line(c,12,19,12,4);line(c,6,10,12,4);line(c,18,10,12,4);line(c,4,16,4,21);line(c,4,21,20,21);line(c,20,21,20,16);break;
            case "receive":line(c,12,3,12,16);line(c,6,10,12,16);line(c,18,10,12,16);line(c,4,17,4,21);line(c,4,21,20,21);line(c,20,21,20,17);break;
            case "home":Path h=new Path();h.moveTo(3,11);h.lineTo(12,3);h.lineTo(21,11);h.lineTo(19,11);h.lineTo(19,21);h.lineTo(5,21);h.lineTo(5,11);h.close();c.drawPath(h,p);break;
            case "plus":line(c,12,4,12,20);line(c,4,12,20,12);break;
            case "stop":c.drawRoundRect(6,6,18,18,2,2,p);break;
            case "info":c.drawCircle(12,12,9,p);line(c,12,11,12,17);c.drawPoint(12,7,p);break;
            case "more":p.setStyle(Paint.Style.FILL);c.drawCircle(12,5,1.4f,p);c.drawCircle(12,12,1.4f,p);c.drawCircle(12,19,1.4f,p);break;
            case "chevron":line(c,9,5,16,12);line(c,16,12,9,19);break;
            case "shield":Path s=new Path();s.moveTo(12,2);s.lineTo(21,6);s.lineTo(20,14);s.quadTo(18,20,12,23);s.quadTo(6,20,4,14);s.lineTo(3,6);s.close();c.drawPath(s,p);line(c,8,12,11,15);line(c,11,15,16,9);break;
            default:Path f=new Path();f.moveTo(3,6);f.lineTo(10,6);f.lineTo(12,9);f.lineTo(21,9);f.lineTo(21,20);f.lineTo(3,20);f.close();c.drawPath(f,p);
        }c.restore();}
    }
}
