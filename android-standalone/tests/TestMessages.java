import de.dennysubke.oniondrop.core.WebText;
import java.nio.file.Path;
import java.util.EnumMap;
import java.util.HashMap;
import java.util.Locale;
import java.util.Map;
import javax.xml.parsers.DocumentBuilderFactory;
import org.w3c.dom.Element;
import org.w3c.dom.NodeList;

/** Exercise the actual shipped translations without requiring Android on the host. */
final class TestMessages {
    static WebText load(String language) throws Exception {
        String folder=language.equals("en")?"values":"values-"+language;
        Path source=Path.of(System.getProperty("oniondrop.res"),folder,"strings.xml");
        DocumentBuilderFactory factory=DocumentBuilderFactory.newInstance();
        factory.setFeature("http://apache.org/xml/features/disallow-doctype-decl",true);
        NodeList nodes=factory.newDocumentBuilder().parse(source.toFile()).getElementsByTagName("string");
        Map<String,String> resources=new HashMap<>();
        for(int i=0;i<nodes.getLength();i++){
            Element node=(Element)nodes.item(i);
            resources.put(node.getAttribute("name"),node.getTextContent().replace("\\'","'"));
        }
        EnumMap<WebText.Key,String> strings=new EnumMap<>(WebText.Key.class);
        for(WebText.Key key:WebText.Key.values())strings.put(key,resources.get("web_"+key.name().toLowerCase(Locale.ROOT)));
        return new WebText(resources.get("web_language"),strings);
    }
}
