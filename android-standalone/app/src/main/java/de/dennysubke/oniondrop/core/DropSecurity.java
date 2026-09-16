package de.dennysubke.oniondrop.core;

import java.net.URLEncoder;
import java.nio.charset.StandardCharsets;
import java.security.*;
import java.util.Base64;

public final class DropSecurity {
    private static final SecureRandom RANDOM=new SecureRandom();
    public static String token(){byte[] bytes=new byte[32];RANDOM.nextBytes(bytes);return Base64.getUrlEncoder().withoutPadding().encodeToString(bytes);}
    public static boolean equal(String a,String b){return a!=null&&b!=null&&MessageDigest.isEqual(a.getBytes(StandardCharsets.UTF_8),b.getBytes(StandardCharsets.UTF_8));}
    public static String html(String s){return s.replace("&","&amp;").replace("<","&lt;").replace(">","&gt;").replace("\"","&quot;").replace("'","&#39;");}
    public static String encode(String s){try{return URLEncoder.encode(s,"UTF-8").replace("+","%20");}catch(Exception impossible){throw new AssertionError(impossible);}}
    public static String filename(String value){
        String name=value==null?"Datei":value.replace('\\','/');
        name=name.substring(name.lastIndexOf('/')+1).replaceAll("[\\p{Cntrl}\\u202A-\\u202E\\u2066-\\u2069]", "_").trim();
        if(name.isEmpty()||name.equals(".")||name.equals(".."))name="Datei";
        if(name.length()>120)name=name.substring(0,120);
        return name;
    }
    public static String hex(byte[] bytes){StringBuilder out=new StringBuilder(bytes.length*2);for(byte b:bytes)out.append(String.format(java.util.Locale.ROOT,"%02x",b&255));return out.toString();}
    private DropSecurity(){}
}
