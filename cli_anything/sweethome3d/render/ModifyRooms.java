import java.io.File;
import java.io.FileInputStream;
import java.io.FileOutputStream;
import java.io.IOException;
import java.lang.reflect.Method;
import java.lang.reflect.Proxy;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Paths;
import java.util.ArrayList;
import java.util.Collections;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;

import javax.swing.undo.UndoableEditSupport;

import com.eteks.sweethome3d.io.ContentRecording;
import com.eteks.sweethome3d.io.DefaultHomeInputStream;
import com.eteks.sweethome3d.io.DefaultHomeOutputStream;
import com.eteks.sweethome3d.io.DefaultUserPreferences;
import com.eteks.sweethome3d.io.HomeXMLExporter;
import com.eteks.sweethome3d.io.HomeXMLHandler;
import com.eteks.sweethome3d.model.Baseboard;
import com.eteks.sweethome3d.model.CatalogTexture;
import com.eteks.sweethome3d.model.Home;
import com.eteks.sweethome3d.model.HomeTexture;
import com.eteks.sweethome3d.model.Level;
import com.eteks.sweethome3d.model.Room;
import com.eteks.sweethome3d.model.TexturesCategory;
import com.eteks.sweethome3d.model.UserPreferences;
import com.eteks.sweethome3d.model.Wall;
import com.eteks.sweethome3d.viewcontroller.RoomController;
import com.eteks.sweethome3d.viewcontroller.ViewFactory;

/**
 * CLI helper: load a .sh3d, apply per-room modifications from a JSON spec, save.
 *
 * Uses SH3D's own RoomController.getRoomsWallSides() (via reflection) for correct
 * interior-wall-face detection — the same algorithm the "Modify rooms" dialog uses.
 *
 * Usage:
 *   java ModifyRooms --in <input.sh3d> --out <output.sh3d> --spec <spec.json>
 *
 * JSON spec format (all fields optional unless noted):
 * {
 *   "rooms": [
 *     {
 *       // One of: "id" (exact) or "match" (predicate applied to all matching rooms)
 *       "id":    "room-<uuid>",
 *       "match": { "level": "Level 0", "min_area_cm2": 50000, "max_area_cm2": 200000 },
 *
 *       "name":            "Kitchen",
 *       "floor_color":     "FFD8C6A4",   // ARGB hex (alpha byte stripped for SH3D)
 *       "floor_texture":   "eTeks#stoneWall", // catalog id; "" to clear; omit/null = leave alone
 *       "floor_visible":   true,
 *       "floor_shiny":     false,
 *       "ceiling_color":   "FFFFFFFF",
 *       "ceiling_texture": "eTeks#stoneTiles",
 *       "ceiling_visible": false,
 *       "ceiling_shiny":   false,
 *
 *       "wall_sides_color":   "FFFFC0CB",  // interior face of every bounding wall
 *       "wall_sides_texture": "eTeks#stoneWall",
 *       "wall_sides_shiny":   false,
 *
 *       "baseboard": {                   // null or absent = leave alone
 *         "color":        "FFFFFFFF",
 *         "texture":      "eTeks#stoneWall",
 *         "thickness_cm": 1.0,
 *         "height_cm":    10.0
 *       }
 *     }
 *   ]
 * }
 */
public class ModifyRooms {

    private static final int LEFT_SIDE  = 0;
    private static final int RIGHT_SIDE = 1;

    // -----------------------------------------------------------------------
    // Entry point
    // -----------------------------------------------------------------------

    public static void main(String[] args) throws Exception {
        String inPath   = null;
        String outPath  = null;
        String specPath = null;

        for (int i = 0; i < args.length - 1; i++) {
            switch (args[i]) {
                case "--in":   inPath   = args[++i]; break;
                case "--out":  outPath  = args[++i]; break;
                case "--spec": specPath = args[++i]; break;
            }
        }

        if (inPath == null || outPath == null || specPath == null) {
            System.err.println("usage: ModifyRooms --in <input.sh3d> --out <output.sh3d> --spec <spec.json>");
            System.exit(2);
        }

        File inFile   = new File(inPath);
        File outFile  = new File(outPath);

        if (!inFile.exists()) {
            System.err.println("error: input not found: " + inPath);
            System.exit(1);
        }
        if (!new File(specPath).exists()) {
            System.err.println("error: spec not found: " + specPath);
            System.exit(1);
        }

        // 1. Load home
        System.out.println("loading " + inFile);
        UserPreferences prefs = new DefaultUserPreferences();
        HomeXMLHandler xmlHandler = new HomeXMLHandler(prefs);
        DefaultHomeInputStream is = new DefaultHomeInputStream(
                new FileInputStream(inFile),
                ContentRecording.INCLUDE_ALL_CONTENT, xmlHandler, prefs, true);
        Home home = is.readHome();
        is.close();
        System.out.println("loaded: rooms=" + home.getRooms().size()
                + " walls=" + home.getWalls().size());

        // 2. Parse spec
        String specJson = new String(Files.readAllBytes(Paths.get(specPath)), StandardCharsets.UTF_8);
        Map<String, Object> spec = (Map<String, Object>) JsonParser.parse(specJson);

        // 3. Apply edits
        int roomsModified = applySpec(home, prefs, spec);
        System.out.println("rooms modified: " + roomsModified);

        // 4. Save — write both the binary "Home" entry AND "Home.xml" so the
        //    output is fully compatible with SH3D's own save format.
        if (outFile.getParentFile() != null) {
            outFile.getParentFile().mkdirs();
        }
        DefaultHomeOutputStream os = new DefaultHomeOutputStream(
                new FileOutputStream(outFile),
                9,
                ContentRecording.INCLUDE_ALL_CONTENT,
                true,                   // serializedHome = true (binary "Home" entry)
                new HomeXMLExporter()); // also write "Home.xml"
        os.writeHome(home);
        os.close();
        System.out.println("wrote " + outFile.getAbsolutePath());

        // 5. Print summary JSON to stdout (last line, parseable by caller)
        System.out.println("{\"rooms_modified\":" + roomsModified
                + ",\"output\":\"" + escapeJson(outFile.getAbsolutePath()) + "\"}");
    }

    // -----------------------------------------------------------------------
    // Core logic
    // -----------------------------------------------------------------------

    @SuppressWarnings("unchecked")
    static int applySpec(Home home, UserPreferences prefs, Map<String, Object> spec) throws Exception {
        List<Object> roomSpecs = (List<Object>) spec.get("rooms");
        if (roomSpecs == null) return 0;

        int count = 0;
        for (Object entry : roomSpecs) {
            Map<String, Object> roomSpec = (Map<String, Object>) entry;
            List<Room> targets = resolveTargets(home, roomSpec);
            for (Room room : targets) {
                applyRoomEdit(home, prefs, room, roomSpec);
                count++;
            }
        }
        return count;
    }

    @SuppressWarnings("unchecked")
    private static List<Room> resolveTargets(Home home, Map<String, Object> roomSpec) {
        if (roomSpec.containsKey("id")) {
            String targetId = (String) roomSpec.get("id");
            for (Room r : home.getRooms()) {
                if (targetId.equals(r.getId())) {
                    return Collections.singletonList(r);
                }
            }
            System.err.println("warning: no room found with id=" + targetId);
            return Collections.emptyList();
        }

        if (roomSpec.containsKey("match")) {
            Map<String, Object> match = (Map<String, Object>) roomSpec.get("match");
            List<Room> result = new ArrayList<>();
            for (Room r : home.getRooms()) {
                if (matchesRoom(r, match)) result.add(r);
            }
            return result;
        }

        System.err.println("warning: room spec entry has neither 'id' nor 'match' — skipping");
        return Collections.emptyList();
    }

    private static boolean matchesRoom(Room room, Map<String, Object> match) {
        if (match.containsKey("level")) {
            String levelName = (String) match.get("level");
            Level level = room.getLevel();
            if (level == null || !levelName.equals(level.getName())) return false;
        }
        if (match.containsKey("min_area_cm2")) {
            double minArea = toDouble(match.get("min_area_cm2"));
            if (room.getArea() < minArea) return false;
        }
        if (match.containsKey("max_area_cm2")) {
            double maxArea = toDouble(match.get("max_area_cm2"));
            if (room.getArea() > maxArea) return false;
        }
        return true;
    }

    @SuppressWarnings("unchecked")
    private static void applyRoomEdit(Home home, UserPreferences prefs,
                                       Room room, Map<String, Object> roomSpec) throws Exception {
        // Name
        if (roomSpec.containsKey("name") && roomSpec.get("name") != null) {
            room.setName((String) roomSpec.get("name"));
        }

        // Floor
        if (roomSpec.containsKey("floor_color") && roomSpec.get("floor_color") != null) {
            room.setFloorColor(parseArgb((String) roomSpec.get("floor_color")));
        }
        if (roomSpec.containsKey("floor_texture")) {
            String catalogId = (String) roomSpec.get("floor_texture");
            if (catalogId == null || catalogId.isEmpty()) {
                room.setFloorTexture(null);
            } else {
                HomeTexture tx = lookupTexture(prefs, catalogId);
                if (tx != null) room.setFloorTexture(tx);
            }
        }
        if (roomSpec.containsKey("floor_visible")) {
            room.setFloorVisible(Boolean.TRUE.equals(roomSpec.get("floor_visible")));
        }
        if (roomSpec.containsKey("floor_shiny")) {
            room.setFloorShininess(Boolean.TRUE.equals(roomSpec.get("floor_shiny")) ? 0.25f : 0.0f);
        }

        // Ceiling
        if (roomSpec.containsKey("ceiling_color") && roomSpec.get("ceiling_color") != null) {
            room.setCeilingColor(parseArgb((String) roomSpec.get("ceiling_color")));
        }
        if (roomSpec.containsKey("ceiling_texture")) {
            String catalogId = (String) roomSpec.get("ceiling_texture");
            if (catalogId == null || catalogId.isEmpty()) {
                room.setCeilingTexture(null);
            } else {
                HomeTexture tx = lookupTexture(prefs, catalogId);
                if (tx != null) room.setCeilingTexture(tx);
            }
        }
        if (roomSpec.containsKey("ceiling_visible")) {
            room.setCeilingVisible(Boolean.TRUE.equals(roomSpec.get("ceiling_visible")));
        }
        if (roomSpec.containsKey("ceiling_shiny")) {
            room.setCeilingShininess(Boolean.TRUE.equals(roomSpec.get("ceiling_shiny")) ? 0.25f : 0.0f);
        }

        // Wall sides and baseboard
        boolean hasWallSides = roomSpec.containsKey("wall_sides_color")
                || roomSpec.containsKey("wall_sides_texture")
                || roomSpec.containsKey("wall_sides_shiny");
        boolean hasBaseboard = roomSpec.containsKey("baseboard") && roomSpec.get("baseboard") != null;

        if (hasWallSides || hasBaseboard) {
            List<Object> wallSides = getWallSidesForRoom(home, prefs, room);
            System.out.println("  room " + room.getId() + ": " + wallSides.size() + " wall sides");

            for (Object ws : wallSides) {
                Wall wall = getWallFromWallSide(ws);
                int  side = getSideFromWallSide(ws);

                if (roomSpec.containsKey("wall_sides_color") && roomSpec.get("wall_sides_color") != null) {
                    int color = parseArgb((String) roomSpec.get("wall_sides_color"));
                    if (side == LEFT_SIDE) {
                        wall.setLeftSideColor(color);
                        wall.setLeftSideTexture(null);
                    } else {
                        wall.setRightSideColor(color);
                        wall.setRightSideTexture(null);
                    }
                }

                if (roomSpec.containsKey("wall_sides_texture")) {
                    String catalogId = (String) roomSpec.get("wall_sides_texture");
                    if (catalogId == null || catalogId.isEmpty()) {
                        if (side == LEFT_SIDE) {
                            wall.setLeftSideTexture(null);
                        } else {
                            wall.setRightSideTexture(null);
                        }
                    } else {
                        HomeTexture tx = lookupTexture(prefs, catalogId);
                        if (tx != null) {
                            if (side == LEFT_SIDE) {
                                wall.setLeftSideTexture(tx);
                                wall.setLeftSideColor(null);
                            } else {
                                wall.setRightSideTexture(tx);
                                wall.setRightSideColor(null);
                            }
                        }
                    }
                }

                if (roomSpec.containsKey("wall_sides_shiny")) {
                    float shininess = Boolean.TRUE.equals(roomSpec.get("wall_sides_shiny")) ? 0.25f : 0.0f;
                    if (side == LEFT_SIDE) {
                        wall.setLeftSideShininess(shininess);
                    } else {
                        wall.setRightSideShininess(shininess);
                    }
                }

                if (hasBaseboard) {
                    Baseboard bb = buildBaseboard((Map<String, Object>) roomSpec.get("baseboard"), prefs);
                    if (side == LEFT_SIDE) {
                        wall.setLeftSideBaseboard(bb);
                    } else {
                        wall.setRightSideBaseboard(bb);
                    }
                }
            }
        }
    }

    // -----------------------------------------------------------------------
    // Wall-side detection via RoomController (reflection)
    // -----------------------------------------------------------------------

    /**
     * Obtain WallSide objects for a room using RoomController.getRoomsWallSides().
     *
     * This is SH3D's own wall-side detection algorithm, accessed via reflection because
     * getRoomsWallSides() is private.  It correctly handles T-junctions, corner walls,
     * external envelope walls, arced walls, and split walls.
     */
    @SuppressWarnings("unchecked")
    private static List<Object> getWallSidesForRoom(Home home, UserPreferences prefs,
                                                      Room room) throws Exception {
        home.setSelectedItems(Collections.singletonList(room));

        // Dynamic proxy stub for ViewFactory — RoomController stores it but only
        // calls into it lazily (when getView() / displayView() is invoked).
        // getRoomsWallSides() does NOT invoke the factory, so returning null/proxies is safe.
        ViewFactory stubFactory = (ViewFactory) Proxy.newProxyInstance(
                ModifyRooms.class.getClassLoader(),
                new Class[]{ ViewFactory.class },
                (proxy, method, margs) -> {
                    Class<?> ret = method.getReturnType();
                    if (ret.isInterface()) {
                        // Return a deeply-stubbed proxy so RoomController can initialise
                        // its BaseboardChoiceController and TextureChoiceController children
                        // without NPEs.
                        return Proxy.newProxyInstance(
                                ModifyRooms.class.getClassLoader(),
                                new Class[]{ ret },
                                (p2, m2, a2) -> {
                                    Class<?> r2 = m2.getReturnType();
                                    if (r2 == boolean.class || r2 == Boolean.class) return false;
                                    if (r2 == int.class    || r2 == Integer.class)  return 0;
                                    if (r2 == float.class  || r2 == Float.class)    return 0.0f;
                                    if (r2 == long.class   || r2 == Long.class)     return 0L;
                                    if (r2.isInterface()) {
                                        return Proxy.newProxyInstance(
                                                ModifyRooms.class.getClassLoader(),
                                                new Class[]{ r2 },
                                                (p3, m3, a3) -> primitiveDefault(m3.getReturnType()));
                                    }
                                    return null;
                                });
                    }
                    return primitiveDefault(ret);
                });

        UndoableEditSupport undoSupport = new UndoableEditSupport();
        RoomController ctrl = new RoomController(home, prefs, stubFactory, null, undoSupport);

        Method m = RoomController.class.getDeclaredMethod("getRoomsWallSides", List.class, List.class);
        m.setAccessible(true);
        return (List<Object>) m.invoke(ctrl, Collections.singletonList(room), null);
    }

    private static Object primitiveDefault(Class<?> type) {
        if (type == boolean.class || type == Boolean.class) return false;
        if (type == int.class    || type == Integer.class)  return 0;
        if (type == float.class  || type == Float.class)    return 0.0f;
        if (type == long.class   || type == Long.class)     return 0L;
        return null;
    }

    private static Wall getWallFromWallSide(Object ws) throws Exception {
        Method m = ws.getClass().getDeclaredMethod("getWall");
        m.setAccessible(true);
        return (Wall) m.invoke(ws);
    }

    private static int getSideFromWallSide(Object ws) throws Exception {
        Method m = ws.getClass().getDeclaredMethod("getSide");
        m.setAccessible(true);
        return (int) m.invoke(ws);
    }

    // -----------------------------------------------------------------------
    // Baseboard
    // -----------------------------------------------------------------------

    private static Baseboard buildBaseboard(Map<String, Object> bbSpec, UserPreferences prefs) {
        float thickness = bbSpec.containsKey("thickness_cm")
                ? (float) toDouble(bbSpec.get("thickness_cm"))
                : prefs.getNewWallBaseboardThickness();
        float height = bbSpec.containsKey("height_cm")
                ? (float) toDouble(bbSpec.get("height_cm"))
                : prefs.getNewWallBaseboardHeight();
        Integer color = bbSpec.containsKey("color") && bbSpec.get("color") != null
                ? parseArgb((String) bbSpec.get("color"))
                : null;
        HomeTexture texture = null;
        if (bbSpec.containsKey("texture")) {
            String catalogId = (String) bbSpec.get("texture");
            if (catalogId != null && !catalogId.isEmpty()) {
                texture = lookupTexture(prefs, catalogId);
            }
        }
        return Baseboard.getInstance(thickness, height, color, texture);
    }

    // -----------------------------------------------------------------------
    // Texture catalog lookup
    // -----------------------------------------------------------------------

    /**
     * Look up a texture by its catalog id (e.g. "eTeks#stoneWall") and return
     * a HomeTexture wrapping it.  Returns null and logs a warning when not found.
     */
    private static HomeTexture lookupTexture(UserPreferences prefs, String catalogId) {
        if (catalogId == null) return null;
        for (TexturesCategory cat : prefs.getTexturesCatalog().getCategories()) {
            for (CatalogTexture tx : cat.getTextures()) {
                if (catalogId.equals(tx.getId())) {
                    return new HomeTexture(tx);
                }
            }
        }
        System.err.println("WARN: texture catalogId not found: " + catalogId);
        return null;
    }

    // -----------------------------------------------------------------------
    // Utilities
    // -----------------------------------------------------------------------

    /**
     * Parse ARGB hex string (e.g. "FFD8C6A4" or "D8C6A4") to SH3D RGB int.
     * SH3D setFloorColor / setLeftSideColor take 0xRRGGBB (no alpha byte).
     */
    static int parseArgb(String hex) {
        hex = hex.trim().replaceFirst("^#", "");
        long v = Long.parseLong(hex, 16);
        if (hex.length() == 8) {
            // Strip the alpha channel — SH3D colours are 0x00RRGGBB
            return (int) (v & 0x00FFFFFFL);
        }
        return (int) (v & 0xFFFFFFFFL);
    }

    static double toDouble(Object o) {
        if (o instanceof Number) return ((Number) o).doubleValue();
        return Double.parseDouble(o.toString());
    }

    private static String escapeJson(String s) {
        return s.replace("\\", "\\\\").replace("\"", "\\\"");
    }

    // -----------------------------------------------------------------------
    // Minimal self-contained JSON parser
    // -----------------------------------------------------------------------
    // Supports: objects {}, arrays [], strings "", numbers, booleans, null.
    // No external dependencies.

    static final class JsonParser {
        private final String src;
        private int pos;

        private JsonParser(String src) {
            this.src = src;
            this.pos = 0;
        }

        static Object parse(String json) {
            return new JsonParser(json.trim()).parseValue();
        }

        private Object parseValue() {
            skipWs();
            char c = peek();
            if (c == '{') return parseObject();
            if (c == '[') return parseArray();
            if (c == '"') return parseString();
            if (c == 't') { consume("true");  return Boolean.TRUE;  }
            if (c == 'f') { consume("false"); return Boolean.FALSE; }
            if (c == 'n') { consume("null");  return null;          }
            return parseNumber();
        }

        private Map<String, Object> parseObject() {
            Map<String, Object> map = new LinkedHashMap<>();
            expect('{');
            skipWs();
            if (peek() == '}') { pos++; return map; }
            while (true) {
                skipWs();
                String key = parseString();
                skipWs();
                expect(':');
                skipWs();
                Object val = parseValue();
                map.put(key, val);
                skipWs();
                char sep = src.charAt(pos++);
                if (sep == '}') break;
                if (sep != ',') throw new RuntimeException("Expected ',' or '}' at " + (pos - 1));
            }
            return map;
        }

        private List<Object> parseArray() {
            List<Object> list = new ArrayList<>();
            expect('[');
            skipWs();
            if (peek() == ']') { pos++; return list; }
            while (true) {
                skipWs();
                list.add(parseValue());
                skipWs();
                char sep = src.charAt(pos++);
                if (sep == ']') break;
                if (sep != ',') throw new RuntimeException("Expected ',' or ']' at " + (pos - 1));
            }
            return list;
        }

        private String parseString() {
            expect('"');
            StringBuilder sb = new StringBuilder();
            while (pos < src.length()) {
                char c = src.charAt(pos++);
                if (c == '"') break;
                if (c == '\\') {
                    char e = src.charAt(pos++);
                    switch (e) {
                        case '"':  sb.append('"');  break;
                        case '\\': sb.append('\\'); break;
                        case '/':  sb.append('/');  break;
                        case 'n':  sb.append('\n'); break;
                        case 'r':  sb.append('\r'); break;
                        case 't':  sb.append('\t'); break;
                        case 'u':
                            int cp = Integer.parseInt(src.substring(pos, pos + 4), 16);
                            sb.append((char) cp);
                            pos += 4;
                            break;
                        default:   sb.append(e);
                    }
                } else {
                    sb.append(c);
                }
            }
            return sb.toString();
        }

        private Number parseNumber() {
            int start = pos;
            if (pos < src.length() && src.charAt(pos) == '-') pos++;
            while (pos < src.length() && Character.isDigit(src.charAt(pos))) pos++;
            boolean isFloat = false;
            if (pos < src.length() && src.charAt(pos) == '.') { isFloat = true; pos++; }
            while (pos < src.length() && Character.isDigit(src.charAt(pos))) pos++;
            if (pos < src.length() && (src.charAt(pos) == 'e' || src.charAt(pos) == 'E')) {
                isFloat = true; pos++;
                if (pos < src.length() && (src.charAt(pos) == '+' || src.charAt(pos) == '-')) pos++;
                while (pos < src.length() && Character.isDigit(src.charAt(pos))) pos++;
            }
            String num = src.substring(start, pos);
            if (isFloat) return Double.parseDouble(num);
            long v = Long.parseLong(num);
            if (v >= Integer.MIN_VALUE && v <= Integer.MAX_VALUE) return (int) v;
            return v;
        }

        private void skipWs() {
            while (pos < src.length() && Character.isWhitespace(src.charAt(pos))) pos++;
        }

        private char peek() {
            if (pos >= src.length()) throw new RuntimeException("Unexpected end of JSON");
            return src.charAt(pos);
        }

        private void expect(char c) {
            if (src.charAt(pos) != c)
                throw new RuntimeException("Expected '" + c + "' at " + pos + " but got '" + src.charAt(pos) + "'");
            pos++;
        }

        private void consume(String token) {
            if (!src.startsWith(token, pos))
                throw new RuntimeException("Expected '" + token + "' at " + pos);
            pos += token.length();
        }
    }
}
