import java.io.File;
import java.io.FileInputStream;
import java.io.FileWriter;
import java.io.IOException;

import javax.media.j3d.BranchGroup;
import javax.media.j3d.Node;

import com.eteks.sweethome3d.io.ContentRecording;
import com.eteks.sweethome3d.io.DefaultHomeInputStream;
import com.eteks.sweethome3d.io.DefaultUserPreferences;
import com.eteks.sweethome3d.io.HomeXMLHandler;
import com.eteks.sweethome3d.j3d.OBJWriter;
import com.eteks.sweethome3d.j3d.Object3DBranchFactory;
import com.eteks.sweethome3d.model.Camera;
import com.eteks.sweethome3d.model.Home;
import com.eteks.sweethome3d.model.HomeEnvironment;
import com.eteks.sweethome3d.model.HomePieceOfFurniture;
import com.eteks.sweethome3d.model.ObserverCamera;
import com.eteks.sweethome3d.model.Room;
import com.eteks.sweethome3d.model.Selectable;
import com.eteks.sweethome3d.model.UserPreferences;
import com.eteks.sweethome3d.model.Wall;
import com.eteks.sweethome3d.viewcontroller.Object3DFactory;

/**
 * CLI helper that exports a SweetHome3D .sh3d file to Wavefront .obj + .mtl
 * using SH3D's bundled OBJWriter.
 *
 * Usage:  java ExportObj input.sh3d output.obj [includeLights]
 *
 * Outputs:
 *   output.obj           – geometry
 *   output.mtl           – materials (written by OBJWriter alongside .obj)
 *   <output>/            – texture PNGs subdirectory (written by OBJWriter)
 *   output.camera.json   – active camera + environment sidecar
 */
public class ExportObj {

    public static void main(String[] args) throws Exception {
        if (args.length < 2) {
            System.err.println("usage: ExportObj input.sh3d output.obj [includeLights]");
            System.exit(2);
        }

        File inFile  = new File(args[0]);
        File objFile = new File(args[1]);
        boolean includeLights = args.length > 2 && Boolean.parseBoolean(args[2]);

        if (!inFile.exists()) {
            System.err.println("error: input file not found: " + inFile);
            System.exit(1);
        }

        // ------------------------------------------------------------------ //
        // 1. Load the Home
        // ------------------------------------------------------------------ //
        System.out.println("loading " + inFile);
        UserPreferences prefs = new DefaultUserPreferences();
        HomeXMLHandler xmlHandler = new HomeXMLHandler(prefs);
        DefaultHomeInputStream is = new DefaultHomeInputStream(
                new FileInputStream(inFile),
                ContentRecording.INCLUDE_ALL_CONTENT,
                xmlHandler, prefs, true);
        Home home = is.readHome();
        is.close();
        System.out.println("home loaded – walls=" + home.getWalls().size()
                + " rooms=" + home.getRooms().size()
                + " furniture=" + home.getFurniture().size());

        // ------------------------------------------------------------------ //
        // 2. Build Java3D scene graph
        // ------------------------------------------------------------------ //
        System.out.println("building Java3D scene graph…");
        Object3DBranchFactory factory = new Object3DBranchFactory(prefs);
        BranchGroup root = new BranchGroup();

        // Walls
        for (Wall wall : home.getWalls()) {
            Object node3d = factory.createObject3D(home, wall, true);
            if (node3d instanceof Node) {
                root.addChild((Node) node3d);
            }
        }

        // Rooms (floors / ceilings)
        for (Room room : home.getRooms()) {
            Object node3d = factory.createObject3D(home, room, true);
            if (node3d instanceof Node) {
                root.addChild((Node) node3d);
            }
        }

        // Furniture (recursive – HomeFurnitureGroup is also Selectable)
        addFurniture(home, home.getFurniture(), factory, root, includeLights);

        System.out.println("scene graph assembled");

        // ------------------------------------------------------------------ //
        // 3. Write .obj + .mtl via OBJWriter
        //    OBJWriter(File, String header, int fractionDigits)
        //    It automatically places the .mtl file and texture dir alongside
        //    the .obj file, using the same base name.
        // ------------------------------------------------------------------ //
        OBJWriter writer = new OBJWriter(objFile,
                "Exported from CLI-Anything-SH3D", 4);
        writer.writeNode(root);
        writer.close();

        // Report produced files
        System.out.println("exported: " + objFile.getAbsolutePath());

        String baseName = objFile.getName();
        int dot = baseName.lastIndexOf('.');
        String stem = (dot >= 0) ? baseName.substring(0, dot) : baseName;

        File parentDir = objFile.getParentFile() != null
                ? objFile.getParentFile()
                : new File(".");

        File mtlFile = new File(parentDir, stem + ".mtl");
        if (mtlFile.exists()) {
            System.out.println("exported: " + mtlFile.getAbsolutePath());
        }

        File texDir = new File(parentDir, stem);
        if (texDir.exists() && texDir.isDirectory()) {
            System.out.println("exported: texture dir " + texDir.getAbsolutePath());
        }

        // ------------------------------------------------------------------ //
        // 4. Write camera + environment sidecar JSON
        // ------------------------------------------------------------------ //
        File cameraJson = new File(parentDir, stem + ".camera.json");
        writeCameraJson(home, cameraJson);
        System.out.println("exported: " + cameraJson.getAbsolutePath());

        System.exit(0);
    }

    // ---------------------------------------------------------------------- //
    // Helpers
    // ---------------------------------------------------------------------- //

    /**
     * Recursively adds furniture nodes to the BranchGroup.
     * HomeFurnitureGroup implements the same HomePieceOfFurniture type and
     * its own getSubGroups()/getFurniture() expands its children, but
     * createObject3D handles groups transparently – we just iterate the flat
     * list that home.getFurniture() returns (which includes top-level items;
     * sub-groups are handled internally by the factory).
     */
    private static void addFurniture(Home home,
            java.util.List<HomePieceOfFurniture> furniture,
            Object3DBranchFactory factory,
            BranchGroup root,
            boolean includeLights) {
        for (HomePieceOfFurniture piece : furniture) {
            // Skip lights unless requested
            if (!includeLights
                    && piece instanceof com.eteks.sweethome3d.model.HomeLight) {
                continue;
            }
            Object node3d = factory.createObject3D(home, piece, true);
            if (node3d instanceof Node) {
                root.addChild((Node) node3d);
            }
        }
    }

    /**
     * Writes a compact JSON sidecar with the active camera and environment.
     * Uses plain string concatenation – no org.json dependency needed.
     */
    private static void writeCameraJson(Home home, File out) throws IOException {
        Camera cam = home.getCamera();
        HomeEnvironment env = home.getEnvironment();

        String camKind = (cam instanceof ObserverCamera)
                ? "observerCamera" : "topCamera";

        // Colors are stored as ARGB ints; format as #AARRGGBB hex strings
        String skyColor    = argbToHex(env.getSkyColor());
        String groundColor = argbToHex(env.getGroundColor());
        String lightColor  = argbToHex(env.getLightColor());

        // wallHeight is in centimetres (SH3D internal units)
        float wallHeight = home.getWallHeight();

        StringBuilder sb = new StringBuilder();
        sb.append("{\n");
        sb.append("  \"camera\": {\n");
        sb.append("    \"kind\": \"").append(camKind).append("\",\n");
        sb.append("    \"x\": ").append(cam.getX()).append(",\n");
        sb.append("    \"y\": ").append(cam.getY()).append(",\n");
        sb.append("    \"z\": ").append(cam.getZ()).append(",\n");
        sb.append("    \"yaw\": ").append(cam.getYaw()).append(",\n");
        sb.append("    \"pitch\": ").append(cam.getPitch()).append(",\n");
        sb.append("    \"fieldOfView\": ").append(cam.getFieldOfView()).append("\n");
        sb.append("  },\n");
        sb.append("  \"environment\": {\n");
        sb.append("    \"skyColor\": \"").append(skyColor).append("\",\n");
        sb.append("    \"groundColor\": \"").append(groundColor).append("\",\n");
        sb.append("    \"lightColor\": \"").append(lightColor).append("\"\n");
        sb.append("  },\n");
        sb.append("  \"wallHeight\": ").append(wallHeight).append("\n");
        sb.append("}\n");

        FileWriter fw = new FileWriter(out);
        fw.write(sb.toString());
        fw.close();
    }

    /** Converts an ARGB int to a "#AARRGGBB" hex string. */
    private static String argbToHex(int argb) {
        return String.format("#%08X", argb);
    }
}
