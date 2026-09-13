// main.cpp - POC #4: a complete, reusable DragonBones character built from
// the walker2 Character Lock - one shared armature with four weighted-mesh
// limbs (front/back leg, front/back arm) plus six rigid parts (head, torso,
// front/back hand, front/back foot), a CharacterAsset/CharacterInstance
// split proving one parsed armature can back multiple independent posed
// instances, a tiny procedural pose API, individual-limb bend tests, a
// 48-frame coordinated walk cycle, and a three-instance scene (one walking,
// one standing, one static) proving the instances do not interfere with
// each other.
//
// Same proven architecture as POC #1/#2/#3: unmodified DragonBones C++
// core, PocRuntime.h glue (PocMeshSlot/PocFactory, copied verbatim from
// POC #3), deterministic explicit frame stepping, headless SFML
// off-screen rendering to PNG. No DragonBones source file is modified.

#include <cmath>
#include <cstdio>
#include <filesystem>
#include <fstream>
#include <memory>
#include <sstream>
#include <string>
#include <vector>

#include <SFML/Graphics.hpp>
#include <rapidjson/document.h>

#include "PocRuntime.h"

using dragonBones::Armature;
using dragonBones::Bone;
using dragonBones::PocFactory;
using dragonBones::PocMeshSlot;

namespace fs = std::filesystem;

static const float DEG2RAD = 3.14159265358979323846f / 180.0f;
static const float RAD2DEG = 180.0f / 3.14159265358979323846f;
static const float PI = 3.14159265358979323846f;
static const float FPS = 24.0f;

static std::string readFile(const std::string& path)
{
    std::ifstream file(path, std::ios::binary);
    if (!file) throw std::runtime_error("Could not open file: " + path);
    std::ostringstream ss;
    ss << file.rdbuf();
    return ss.str();
}

// ---------------------------------------------------------------------------
// CharacterAsset: the parsed-once, shared data. Corresponds directly to
// DragonBones' own ArmatureData (parsed by factory.parseDragonBonesData) -
// factory.buildArmature() can be called on it as many times as needed to
// produce independent instances (requirement 4: "CharacterAsset !=
// CharacterInstance"). Also owns the rigid-part textures (shared, read-only
// pixel data - fine to share across instances) and each mesh slot's
// triangle-index list (read directly from character_ske.json since main.cpp
// needs it to build SFML vertex arrays; PocMeshSlot itself only exposes the
// already-deformed vertex positions, not the index list).
// ---------------------------------------------------------------------------
struct MeshInfo
{
    std::string slotName;
    std::vector<unsigned> triangleIndices;
};

struct RigidPartInfo
{
    std::string component;
    std::string boneName;
    float pivotX = 0.f, pivotY = 0.f;
    sf::Texture texture;
};

struct CharacterAsset
{
    PocFactory factory;
    std::vector<MeshInfo> meshes;
    std::vector<RigidPartInfo> rigidParts;
    float rootRestX = 0.f, rootRestY = 0.f;

    bool load(const std::string& skeletonPath, const std::string& manifestPath)
    {
        const std::string skeletonJson = readFile(skeletonPath);
        auto* data = factory.parseDragonBonesData(skeletonJson.c_str());
        if (data == nullptr)
        {
            std::fprintf(stderr, "Failed to parse %s\n", skeletonPath.c_str());
            return false;
        }

        rapidjson::Document doc;
        doc.Parse(skeletonJson.c_str());
        const auto& armatureJson = doc["armature"][0];

        for (const auto& b : armatureJson["bone"].GetArray())
        {
            if (std::string(b["name"].GetString()) == "root")
            {
                rootRestX = static_cast<float>(b["transform"]["x"].GetDouble());
                rootRestY = static_cast<float>(b["transform"]["y"].GetDouble());
            }
        }

        for (const auto& slotJson : armatureJson["skin"][0]["slot"].GetArray())
        {
            MeshInfo info;
            info.slotName = slotJson["name"].GetString();
            const auto& mesh = slotJson["display"][0];
            for (const auto& v : mesh["triangles"].GetArray())
            {
                info.triangleIndices.push_back(v.GetUint());
            }
            meshes.push_back(std::move(info));
        }

        const std::string manifestJson = readFile(manifestPath);
        rapidjson::Document mdoc;
        mdoc.Parse(manifestJson.c_str());
        for (const auto& p : mdoc["parts"].GetArray())
        {
            RigidPartInfo part;
            part.component = p["component"].GetString();
            part.boneName = p["bone"].GetString();
            part.pivotX = static_cast<float>(p["pivot_x"].GetDouble());
            part.pivotY = static_cast<float>(p["pivot_y"].GetDouble());
            if (!part.texture.loadFromFile(p["file"].GetString()))
            {
                std::fprintf(stderr, "Failed to load %s\n", p["file"].GetString());
                return false;
            }
            part.texture.setSmooth(true);
            rigidParts.push_back(std::move(part));
        }

        return true;
    }

    Armature* buildInstanceArmature()
    {
        return factory.buildArmature("Walker2Character");
    }
};

// ---------------------------------------------------------------------------
// CharacterInstance: one independently posed, positioned character built
// from a CharacterAsset. Owns its OWN Armature (its own Bone/Slot objects -
// factory.buildArmature() creates a fresh instance each call even though the
// underlying ArmatureData came from parsing the JSON only once), its own
// world transform (position/heading), its own action/animation time, and
// its own rigid-part sprites (sf::Sprite state per instance, referencing
// the ASSET's shared textures). Nothing here is shared mutable state between
// instances - this is what step 8/9's "no cross-character contamination"
// requirement depends on.
// ---------------------------------------------------------------------------
struct CharacterInstance
{
    CharacterAsset* asset = nullptr;
    Armature* armature = nullptr;
    std::vector<PocMeshSlot*> meshSlots;      // parallel to asset->meshes
    std::vector<Bone*> rigidBones;            // parallel to asset->rigidParts
    std::vector<sf::Sprite> rigidSprites;     // parallel to asset->rigidParts

    float worldX = 0.f, worldY = 0.f;
    float heading = 1.f; // +1 = default facing, -1 = mirrored about own root
    std::string action = "stand"; // "stand" | "walk" | "static"
    float animTime = 0.f;

    void init(CharacterAsset* a, float x, float y, float headingDir, const std::string& initialAction)
    {
        asset = a;
        worldX = x;
        worldY = y;
        heading = headingDir;
        action = initialAction;

        armature = asset->buildInstanceArmature();

        for (const auto& m : asset->meshes)
        {
            meshSlots.push_back(dynamic_cast<PocMeshSlot*>(armature->getSlot(m.slotName)));
        }
        for (const auto& p : asset->rigidParts)
        {
            Bone* bone = armature->getBone(p.boneName);
            rigidBones.push_back(bone);
            sf::Sprite sprite;
            sprite.setTexture(p.texture);
            sprite.setOrigin(p.pivotX, p.pivotY);
            rigidSprites.push_back(sprite);
        }
    }

    // --- Procedural pose API (requirement 5) ---
    void setBoneRotation(const std::string& boneName, float angleDeg)
    {
        Bone* b = armature->getBone(boneName);
        if (b != nullptr) b->offset.rotation = angleDeg * DEG2RAD;
    }

    void setBonePosition(const std::string& boneName, float x, float y)
    {
        Bone* b = armature->getBone(boneName);
        if (b != nullptr)
        {
            b->offset.x = x;
            b->offset.y = y;
        }
    }

    void setHeading(float direction) { heading = direction; }

    void resetPose()
    {
        for (Bone* b : armature->getBones())
        {
            b->offset.rotation = 0.f;
            b->offset.x = 0.f;
            b->offset.y = 0.f;
        }
    }

    // Evaluates this instance's current action into bone offsets at time t
    // (seconds). "stand": rest pose, no motion. "walk": the coordinated
    // 4-limb walk cycle (requirement 7). "static": a fixed non-rest pose,
    // independent of time (requirement 12 - proves a second, differently
    // posed instance from the SAME asset).
    void evaluatePose(float t)
    {
        resetPose();

        if (action == "stand")
        {
            return;
        }

        if (action == "static")
        {
            // A fixed, clearly non-rest pose (arms partly raised, one knee
            // bent) held indefinitely - proves the same CharacterAsset can
            // back an instance with an entirely different, independent pose
            // from the walking/standing instances, with no animation clock.
            setBoneRotation("upper_arm_front", -20.f);
            setBoneRotation("forearm_front", -25.f);
            setBoneRotation("upper_arm_back", 15.f);
            setBoneRotation("forearm_back", 10.f);
            setBoneRotation("thigh_front", 10.f);
            setBoneRotation("shin_front", 20.f);
            return;
        }

        // action == "walk"
        // 1.0 Hz over the 2s/48-frame render = exactly 2 full gait cycles,
        // so frame 0 and frame 47 (t=1.9583s, one frame short of the 2nd
        // cycle closing) land within ~15 degrees of phase of each other -
        // "approximately" cyclic per requirement 11, not a coincidence of
        // an arbitrary frequency.
        const float STRIDE_FREQ = 1.0f; // Hz - full gait cycles per second
        const float phase = 2.0f * PI * STRIDE_FREQ * t;

        const float thighF = 30.f * std::sin(phase);
        const float thighB = 30.f * std::sin(phase + PI);

        // Knee/elbow bends are one-directional (never hyperextend) and lag
        // a quarter cycle behind their proximal bone, so the foot lifts
        // clear of the ground during the forward swing and the leg is
        // straight during stance - mechanically coordinated, not an
        // artistic target.
        const float shinF = 22.f * std::max(0.f, std::sin(phase + PI / 2.f));
        const float shinB = 22.f * std::max(0.f, std::sin(phase + PI + PI / 2.f));

        const float upperArmF = 26.f * std::sin(phase + PI); // opposite same-side leg
        const float upperArmB = 26.f * std::sin(phase);
        const float forearmF = 14.f * std::max(0.f, std::sin(phase + PI + PI / 2.f));
        const float forearmB = 14.f * std::max(0.f, std::sin(phase + PI / 2.f));

        const float hipBounce = -6.f * std::fabs(std::sin(phase));
        const float torsoStabilize = -3.f * std::sin(phase);
        const float headStabilize = 1.5f * std::sin(phase);

        setBoneRotation("thigh_front", thighF);
        setBoneRotation("shin_front", shinF);
        setBoneRotation("thigh_back", thighB);
        setBoneRotation("shin_back", shinB);
        setBoneRotation("upper_arm_front", upperArmF);
        setBoneRotation("forearm_front", forearmF);
        setBoneRotation("upper_arm_back", upperArmB);
        setBoneRotation("forearm_back", forearmB);
        setBoneRotation("torso", torsoStabilize);
        setBoneRotation("head", headStabilize);
        setBonePosition("root", 0.f, hipBounce);
    }

    // Advances this instance's OWN armature by one frame and refreshes its
    // OWN mesh slots. Touches nothing belonging to any other instance.
    void advance(float dt)
    {
        for (Bone* b : armature->getBones())
        {
            b->invalidUpdate();
        }
        armature->advanceTime(dt);
        for (PocMeshSlot* slot : meshSlots)
        {
            if (slot != nullptr) slot->update(-1);
        }
    }

    // World-space transform for one point in this character's own rest
    // coordinate system: mirror about the character's own root (heading),
    // then translate so the root lands at (worldX, worldY).
    sf::Vector2f toWorld(float x, float y) const
    {
        const float localX = (x - asset->rootRestX) * heading;
        const float localY = (y - asset->rootRestY);
        return sf::Vector2f(worldX + localX, worldY + localY);
    }

    void draw(sf::RenderTarget& target)
    {
        for (std::size_t i = 0; i < meshSlots.size(); ++i)
        {
            PocMeshSlot* slot = meshSlots[i];
            if (slot == nullptr) continue;
            const auto& indices = asset->meshes[i].triangleIndices;
            const auto& verts = slot->deformedVertices;
            sf::VertexArray tris(sf::Triangles, indices.size());
            for (std::size_t k = 0; k < indices.size(); ++k)
            {
                const auto idx = indices[k];
                const sf::Vector2f p = toWorld(verts[idx * 2], verts[idx * 2 + 1]);
                tris[k].position = p;
                tris[k].color = sf::Color(110, 140, 190, 255);
            }
            target.draw(tris);
        }

        for (std::size_t i = 0; i < rigidBones.size(); ++i)
        {
            Bone* bone = rigidBones[i];
            if (bone == nullptr) continue;
            bone->updateGlobalTransform();
            const sf::Vector2f p = toWorld(bone->global.x, bone->global.y);
            sf::Sprite& sprite = rigidSprites[i];
            sprite.setPosition(p);
            sprite.setRotation(bone->offset.rotation * RAD2DEG * heading);
            sprite.setScale(heading, 1.f);
            target.draw(sprite);
        }
    }

    // Numeric state dump (requirements 8/9/10/13/14 need ground truth, not
    // just pixels): bone rotation deltas, world-space bone positions, the
    // distal-most rigid part's world position (foot/hand), and each mesh
    // slot's own deformed vertex list, so verify.py can check independence,
    // limb attachment, and per-frame pose change numerically rather than by
    // pixel heuristics.
    void dumpState(std::ostream& out) const
    {
        out << "{";
        out << "\"action\":\"" << action << "\",";
        out << "\"worldX\":" << worldX << ",\"worldY\":" << worldY << ",\"heading\":" << heading << ",";

        out << "\"bones\":{";
        bool first = true;
        for (Bone* b : armature->getBones())
        {
            if (!first) out << ",";
            first = false;
            out << "\"" << b->getName() << "\":{\"rotationDeg\":" << (b->offset.rotation * RAD2DEG)
                << ",\"globalX\":" << b->global.x << ",\"globalY\":" << b->global.y << "}";
        }
        out << "},";

        out << "\"rigidParts\":{";
        first = true;
        for (std::size_t i = 0; i < rigidBones.size(); ++i)
        {
            if (rigidBones[i] == nullptr) continue;
            if (!first) out << ",";
            first = false;
            const sf::Vector2f p = toWorld(rigidBones[i]->global.x, rigidBones[i]->global.y);
            out << "\"" << asset->rigidParts[i].component << "\":[" << p.x << "," << p.y << "]";
        }
        out << "},";

        out << "\"meshes\":{";
        first = true;
        for (std::size_t i = 0; i < meshSlots.size(); ++i)
        {
            if (meshSlots[i] == nullptr) continue;
            if (!first) out << ",";
            first = false;
            out << "\"" << asset->meshes[i].slotName << "\":[";
            const auto& verts = meshSlots[i]->deformedVertices;
            for (std::size_t v = 0; v < verts.size(); v += 2)
            {
                if (v > 0) out << ",";
                const sf::Vector2f p = toWorld(verts[v], verts[v + 1]);
                out << "[" << p.x << "," << p.y << "]";
            }
            out << "]";
        }
        out << "}";
        out << "}";
    }
};

int main()
{
    fs::create_directories("output");
    fs::create_directories("output/limb_tests");
    fs::create_directories("output/dump");

    CharacterAsset asset;
    if (!asset.load("character_ske.json", "parts_manifest.json")) return 1;
    std::printf("Loaded asset: %zu mesh slots, %zu rigid parts\n", asset.meshes.size(), asset.rigidParts.size());

    // ------------------------------------------------------------------
    // Step 6: individual limb bend tests, one dedicated instance, one
    // frame per (limb, angle) - 4 limbs x 4 angles = 16 renders. Verifies
    // no tearing / no detachment / smooth deformation / correct pivot
    // BEFORE attempting the full coordinated walk.
    // ------------------------------------------------------------------
    {
        CharacterInstance testChar;
        testChar.init(&asset, 400.f, 250.f, 1.f, "stand");

        const unsigned W = 800, H = 700;
        sf::RenderTexture rt;
        rt.create(W, H);
        sf::View view(sf::FloatRect(0.f, 0.f, static_cast<float>(W), static_cast<float>(H)));
        rt.setView(view);

        struct LimbTest { std::string name, proximal, distal; };
        const std::vector<LimbTest> limbs = {
            {"front_leg", "thigh_front", "shin_front"},
            {"back_leg", "thigh_back", "shin_back"},
            {"front_arm", "upper_arm_front", "forearm_front"},
            {"back_arm", "upper_arm_back", "forearm_back"},
        };
        const float angles[] = {0.f, 15.f, 30.f, 45.f};

        for (const auto& limb : limbs)
        {
            for (float angle : angles)
            {
                testChar.resetPose();
                testChar.setBoneRotation(limb.proximal, angle);
                testChar.setBoneRotation(limb.distal, angle);
                testChar.advance(1.f / FPS);

                rt.clear(sf::Color(235, 235, 230, 255));
                testChar.draw(rt);
                rt.display();

                char filename[128];
                std::snprintf(filename, sizeof(filename), "output/limb_tests/%s_%03.0f.png", limb.name.c_str(), angle);
                sf::Image img = rt.getTexture().copyToImage();
                if (!img.saveToFile(filename))
                {
                    std::fprintf(stderr, "Failed to save %s\n", filename);
                    return 1;
                }
                std::printf("wrote %s\n", filename);
            }
        }
    }

    // ------------------------------------------------------------------
    // Steps 7-9-12: three independent instances from the SAME
    // CharacterAsset, one shared 48-frame render pass, 1200x700 canvas.
    //   Character 1: x=350, walking (48-frame coordinated cycle)
    //   Character 2: x=850, standing, mirrored heading (proves setHeading
    //                is per-instance and independent of Character 1/3)
    //   Character 3: x=600 (center), static pose (proves the SAME asset
    //                supports a third, differently-posed instance)
    // ------------------------------------------------------------------
    const unsigned WIDTH = 1200, HEIGHT = 700;
    const int FRAME_COUNT = 48;

    // The character (head top to foot bottom, from the Character Lock's own
    // proportions) spans roughly 1250px vertically at 1:1 scale - taller
    // than the requested 700px canvas. Rather than crop the head (as a
    // first render of this scene did), the SFML *view* covers a larger
    // world rect than the 1200x700 framebuffer, zooming the whole scene out
    // just enough for head-to-foot to fit with margin, while the rendered
    // PNG stays exactly 1200x700 pixels as required. View aspect ratio is
    // kept equal to WIDTH/HEIGHT so nothing stretches.
    const float VIEW_HEIGHT = 1350.f;
    const float VIEW_WIDTH = VIEW_HEIGHT * (static_cast<float>(WIDTH) / static_cast<float>(HEIGHT));
    const float VIEW_TOP = -100.f;
    const float ROOT_Y = 650.f;

    CharacterInstance char1, char2, char3;
    char1.init(&asset, 0.2917f * VIEW_WIDTH, ROOT_Y, 1.f, "walk");
    char2.init(&asset, 0.7083f * VIEW_WIDTH, ROOT_Y, -1.f, "stand");
    char3.init(&asset, 0.5000f * VIEW_WIDTH, ROOT_Y, 1.f, "static");

    sf::RenderTexture renderTexture;
    if (!renderTexture.create(WIDTH, HEIGHT))
    {
        std::fprintf(stderr, "Failed to create %ux%u RenderTexture\n", WIDTH, HEIGHT);
        return 1;
    }
    sf::View view(sf::FloatRect(0.f, VIEW_TOP, VIEW_WIDTH, VIEW_HEIGHT));
    renderTexture.setView(view);

    for (int frame = 0; frame < FRAME_COUNT; ++frame)
    {
        const float t = static_cast<float>(frame) / FPS;

        char1.evaluatePose(t);
        char2.evaluatePose(t); // "stand" -> resets to rest regardless of t
        char3.evaluatePose(t); // "static" -> same fixed pose regardless of t

        char1.advance(1.f / FPS);
        char2.advance(1.f / FPS);
        char3.advance(1.f / FPS);

        renderTexture.clear(sf::Color(235, 235, 230, 255));
        char1.draw(renderTexture);
        char2.draw(renderTexture);
        char3.draw(renderTexture);
        renderTexture.display();

        char filename[64];
        std::snprintf(filename, sizeof(filename), "output/frame_%04d.png", frame);
        sf::Image image = renderTexture.getTexture().copyToImage();
        if (!image.saveToFile(filename))
        {
            std::fprintf(stderr, "Failed to save %s\n", filename);
            return 1;
        }

        char dumpFilename[64];
        std::snprintf(dumpFilename, sizeof(dumpFilename), "output/dump/frame_%04d.json", frame);
        std::ofstream dumpOut(dumpFilename);
        dumpOut << "{\"char1\":";
        char1.dumpState(dumpOut);
        dumpOut << ",\"char2\":";
        char2.dumpState(dumpOut);
        dumpOut << ",\"char3\":";
        char3.dumpState(dumpOut);
        dumpOut << "}";

        std::printf("wrote %s (t=%.4fs)\n", filename, t);
    }

    char1.armature->dispose();
    char2.armature->dispose();
    char3.armature->dispose();
    std::printf("Done: 16 limb-test frames + %d scene frames written to output/\n", FRAME_COUNT);
    return 0;
}
