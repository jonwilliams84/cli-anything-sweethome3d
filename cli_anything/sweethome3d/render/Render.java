import java.awt.image.BufferedImage;
import java.io.File;
import java.io.FileInputStream;
import javax.imageio.ImageIO;

import com.eteks.sweethome3d.io.DefaultHomeInputStream;
import com.eteks.sweethome3d.io.ContentRecording;
import com.eteks.sweethome3d.io.HomeXMLHandler;
import com.eteks.sweethome3d.io.DefaultUserPreferences;
import com.eteks.sweethome3d.model.Home;
import com.eteks.sweethome3d.model.Camera;
import com.eteks.sweethome3d.model.UserPreferences;
import com.eteks.sweethome3d.j3d.PhotoRenderer;
import com.eteks.sweethome3d.j3d.PhotoRenderer.Quality;

public class Render {
  public static void main(String[] args) throws Exception {
    if (args.length < 2) {
      System.err.println("usage: Render input.sh3d output.png [w] [h] [quality]");
      System.exit(2);
    }
    File in = new File(args[0]);
    File out = new File(args[1]);
    int w = args.length > 2 ? Integer.parseInt(args[2]) : 1600;
    int h = args.length > 3 ? Integer.parseInt(args[3]) : 1000;
    // PhotoRenderer.Quality only has LOW and HIGH in SH3D 7.5.
    // MEDIUM maps to HIGH as a reasonable approximation.
    String qualityArg = args.length > 4 ? args[4].toUpperCase() : "LOW";
    Quality quality;
    switch (qualityArg) {
      case "HIGH":
      case "MEDIUM":
        quality = Quality.HIGH;
        break;
      default:
        quality = Quality.LOW;
        break;
    }

    System.out.println("loading " + in);
    UserPreferences prefs = new DefaultUserPreferences();
    HomeXMLHandler xml = new HomeXMLHandler(prefs);
    DefaultHomeInputStream is = new DefaultHomeInputStream(
        new FileInputStream(in),
        ContentRecording.INCLUDE_ALL_CONTENT,
        xml, prefs, true);
    Home home = is.readHome();
    is.close();

    Camera cam = home.getCamera();
    System.out.printf("camera %s x=%.1f y=%.1f z=%.1f yaw=%.3f pitch=%.3f%n",
        cam.getClass().getSimpleName(),
        cam.getX(), cam.getY(), cam.getZ(), cam.getYaw(), cam.getPitch());

    BufferedImage img = new BufferedImage(w, h, BufferedImage.TYPE_INT_RGB);
    System.out.println("rendering " + w + "x" + h + " ...");
    PhotoRenderer renderer = new PhotoRenderer(home, quality);
    renderer.render(img, cam, null);
    renderer.dispose();
    ImageIO.write(img, "png", out);
    System.out.println("wrote " + out);
  }
}
