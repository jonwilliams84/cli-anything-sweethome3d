import java.io.FileInputStream;
import com.eteks.sweethome3d.io.ContentRecording;
import com.eteks.sweethome3d.io.DefaultHomeInputStream;
import com.eteks.sweethome3d.io.DefaultUserPreferences;
import com.eteks.sweethome3d.io.HomeXMLHandler;
import com.eteks.sweethome3d.model.Home;
import com.eteks.sweethome3d.model.UserPreferences;

/**
 * Minimal CLI validator: opens a .sh3d with Sweet Home 3D's own reader.
 * Exit 0 if the file loads, non-zero otherwise (e.g. DamagedHomeIOException).
 */
public class ValidateSh3d {
    public static void main(String[] args) throws Exception {
        if (args.length < 1) {
            System.err.println("usage: ValidateSh3d file.sh3d");
            System.exit(2);
        }
        UserPreferences prefs = new DefaultUserPreferences();
        HomeXMLHandler xmlHandler = new HomeXMLHandler(prefs);
        DefaultHomeInputStream is = new DefaultHomeInputStream(
            new FileInputStream(args[0]),
            ContentRecording.INCLUDE_ALL_CONTENT,
            xmlHandler, prefs, true);
        Home home = is.readHome();
        is.close();
        System.out.println("OK walls=" + home.getWalls().size()
            + " rooms=" + home.getRooms().size()
            + " furniture=" + home.getFurniture().size());
    }
}
