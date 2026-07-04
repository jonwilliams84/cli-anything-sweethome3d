import java.io.BufferedReader;
import java.io.File;
import java.io.FileInputStream;
import java.io.FileReader;
import java.io.FileWriter;
import java.io.IOException;
import java.io.PrintWriter;
import java.text.NumberFormat;
import java.util.Locale;

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
        // ------------------------------------------------------------------
        // BUG 1 FIX: SH3D's OBJWriter uses NumberFormat.getNumberInstance(Locale.US)
        // which has grouping enabled by default → values ≥1000 get comma
        // separators (e.g. "1,350.1787"), corrupting the OBJ for Blender's
        // importer (strtod stops at the comma, vertices collapse).
        // Setting Locale.ROOT (or Locale.US with grouping disabled) prevents this.
        // We also set the default locale BEFORE constructing OBJWriter so the
        // internal NumberFormat.getNumberInstance() call picks up the root locale.
        // ------------------------------------------------------------------
        Locale.setDefault(Locale.ROOT);

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

        // Walls — skip those on invisible levels (BUG 5: level filter)
        int wallCount = 0;
        for (Wall wall : home.getWalls()) {
            if (wall.getLevel() != null && !wall.getLevel().isViewableAndVisible()) {
                continue;
            }
            Object node3d = factory.createObject3D(home, wall, true);
            if (node3d instanceof Node) {
                root.addChild((Node) node3d);
                wallCount++;
            }
        }

        // Rooms (floors / ceilings) — skip those on invisible levels
        int roomCount = 0;
        for (Room room : home.getRooms()) {
            if (room.getLevel() != null && !room.getLevel().isViewableAndVisible()) {
                continue;
            }
            Object node3d = factory.createObject3D(home, room, true);
            if (node3d instanceof Node) {
                root.addChild((Node) node3d);
                roomCount++;
            }
        }

        // Furniture (recursive – HomeFurnitureGroup is also Selectable)
        int furnCount = addFurniture(home, home.getFurniture(), factory, root, includeLights);

        System.out.println("scene graph assembled – walls=" + wallCount
                + " rooms=" + roomCount + " furniture=" + furnCount);

        // ------------------------------------------------------------------ //
        // 3. Write .obj + .mtl via OBJWriter
        //    OBJWriter(File, String header, int fractionDigits)
        //    It automatically places the .mtl file and texture dir alongside
        //    the .obj file, using the same base name.
        // ------------------------------------------------------------------ //
        OBJWriter writer = new OBJWriter(objFile,
                "Exported from CLI-Anything-SH3D", 4);

        // BUG 1 FIX (belt-and-suspenders): OBJWriter internally creates a
        // NumberFormat with NumberFormat.getNumberInstance(Locale.US) which
        // has grouping enabled → comma separators for values ≥1000. Use
        // reflection to reach the private `numberFormat` field and disable
        // grouping, so vertex/normal/UV coordinates are written as plain
        // numbers (e.g. "1350.1787" not "1,350.1787").
        try {
            java.lang.reflect.Field nfField =
                    OBJWriter.class.getDeclaredField("numberFormat");
            nfField.setAccessible(true);
            NumberFormat nf = (NumberFormat) nfField.get(writer);
            if (nf != null) {
                nf.setGroupingUsed(false);
                System.out.println("disabled number grouping in OBJWriter");
            }
        } catch (Exception reflectEx) {
            // Reflection can fail on restricted JVMs; the post-process
            // safety net below still catches any stray commas.
            System.out.println("note: could not patch OBJWriter numberFormat ("
                    + reflectEx.getMessage() + "); will post-process");
        }

        writer.writeNode(root);
        writer.close();

        // BUG 1 SAFtey net: post-process the OBJ to strip any remaining
        // thousands-separator commas from vertex/normal/UV lines.
        // This catches the case where reflection fails or the internal
        // defaultNumberFormat (used for exponential notation) still groups.
        stripGroupingCommas(objFile);

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
    private static int addFurniture(Home home,
            java.util.List<HomePieceOfFurniture> furniture,
            Object3DBranchFactory factory,
            BranchGroup root,
            boolean includeLights) {
        int count = 0;
        for (HomePieceOfFurniture piece : furniture) {
            // Skip lights unless requested
            if (!includeLights
                    && piece instanceof com.eteks.sweethome3d.model.HomeLight) {
                continue;
            }
            // BUG 5: skip furniture on invisible levels
            if (piece.getLevel() != null && !piece.getLevel().isViewableAndVisible()) {
                continue;
            }
            Object node3d = factory.createObject3D(home, piece, true);
            if (node3d instanceof Node) {
                root.addChild((Node) node3d);
                count++;
            }
        }
        return count;
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

    /**
     * BUG 1 safety net: strip thousands-separator commas from vertex/normal/UV
     * lines in the OBJ file. OBJWriter's NumberFormat may still group numbers
     * ≥1000 (e.g. "1,350.1787") even after the reflection patch, because the
     * internal defaultNumberFormat (used for exponential notation) uses a
     * different DecimalFormat. Blender's OBJ importer misparses grouped numbers
     * (strtod stops at the comma), causing far-side vertices to collapse.
     *
     * This pass rewrites v/vn/vt/f lines, removing commas that appear between
     * digits (thousands separators), while preserving the structural commas in
     * face lines (which separate vertex/texture/normal indices like "1/2/3").
     */
    private static void stripGroupingCommas(File objFile) throws IOException {
        File tmp = new File(objFile.getAbsolutePath() + ".tmp");
        boolean changed = false;
        try (BufferedReader r = new BufferedReader(new FileReader(objFile));
             PrintWriter w = new PrintWriter(tmp)) {
            String line;
            while ((line = r.readLine()) != null) {
                String fixed = fixObjLine(line);
                if (!fixed.equals(line)) changed = true;
                w.println(fixed);
            }
        }
        if (changed) {
            if (!objFile.delete() || !tmp.renameTo(objFile)) {
                throw new IOException("could not replace " + objFile
                        + " with comma-stripped version");
            }
            System.out.println("stripped grouping commas from OBJ: " + objFile);
        } else {
            tmp.delete();
        }
    }

    /**
     * Remove thousands-separator commas from v, vn, vt lines.
     * Face lines (f) use slashes, not commas, so they're left alone.
     * Comment lines (#) are left alone.
     */
    private static String fixObjLine(String line) {
        if (line.isEmpty()) return line;
        char c = line.charAt(0);
        // v, vn, vt lines have numeric coords that may contain grouping commas
        if (c == 'v' && (line.length() == 1 || line.charAt(1) == ' '
                || line.charAt(1) == 'n' || line.charAt(1) == 't')) {
            return stripCommasFromNumbers(line);
        }
        return line;
    }

    /**
     * Remove commas that sit between digits (thousands separators).
     * "v 17.0609 0 1,350.1787" → "v 17.0609 0 1350.1787"
     */
    private static String stripCommasFromNumbers(String s) {
        StringBuilder sb = new StringBuilder(s.length());
        for (int i = 0; i < s.length(); i++) {
            char ch = s.charAt(i);
            if (ch == ',') {
                // Only remove if surrounded by digits (thousands separator)
                boolean prevDigit = i > 0 && Character.isDigit(s.charAt(i - 1));
                boolean nextDigit = i + 1 < s.length()
                        && Character.isDigit(s.charAt(i + 1));
                if (prevDigit && nextDigit) {
                    continue; // skip this comma
                }
            }
            sb.append(ch);
        }
        return sb.toString();
    }
}
