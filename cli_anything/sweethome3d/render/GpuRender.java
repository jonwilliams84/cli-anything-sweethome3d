import java.awt.image.BufferedImage;
import java.io.File;
import java.io.FileInputStream;
import javax.imageio.ImageIO;
import javax.swing.JFrame;

import com.eteks.sweethome3d.io.DefaultHomeInputStream;
import com.eteks.sweethome3d.io.ContentRecording;
import com.eteks.sweethome3d.io.HomeXMLHandler;
import com.eteks.sweethome3d.io.DefaultUserPreferences;
import com.eteks.sweethome3d.model.Home;
import com.eteks.sweethome3d.model.UserPreferences;
import com.eteks.sweethome3d.swing.HomeComponent3D;

public class GpuRender {
    public static void main(String[] args) throws Exception {
        if (args.length < 2) {
            System.err.println("usage: GpuRender input.sh3d output.png [w] [h]");
            System.exit(2);
        }
        File in = new File(args[0]);
        File out = new File(args[1]);
        int w = args.length > 2 ? Integer.parseInt(args[2]) : 1400;
        int h = args.length > 3 ? Integer.parseInt(args[3]) : 900;

        System.out.println("loading " + in);
        UserPreferences prefs = new DefaultUserPreferences();
        HomeXMLHandler xml = new HomeXMLHandler(prefs);
        DefaultHomeInputStream is = new DefaultHomeInputStream(
            new FileInputStream(in), ContentRecording.INCLUDE_ALL_CONTENT,
            xml, prefs, true);
        Home home = is.readHome();
        is.close();

        System.out.println("building Java3D scene…");
        JFrame frame = new JFrame("offscreen render");
        HomeComponent3D comp = new HomeComponent3D(home, prefs, false);
        frame.add(comp);
        frame.setSize(w, h);
        frame.setVisible(false);
        // Force layout so the 3D scene initialises before we capture.
        frame.pack();

        System.out.println("rendering " + w + "x" + h + " via GPU/JOGL…");
        comp.startOffscreenImagesCreation();
        try {
            BufferedImage img = comp.getOffScreenImage(w, h);
            ImageIO.write(img, "png", out);
            System.out.println("wrote " + out);
        } finally {
            comp.endOffscreenImagesCreation();
            frame.dispose();
        }
        System.exit(0);  // Java3D leaves threads alive
    }
}
