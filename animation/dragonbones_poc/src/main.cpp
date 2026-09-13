// main.cpp - POC #2: Character Lock -> DragonBones asset -> procedural pose
// -> rendered frames, for the walker2 Character Lock.
//
// Reuses the exact architecture proven in DragonBonesCPP/poc (unmodified
// DragonBones C++ core, PocRuntime.h glue, deterministic frame stepping,
// headless SFML off-screen rendering to PNG). The only difference from
// that POC: instead of drawing primitive rectangles per bone, this program
// draws one sf::Sprite per rigid rasterized Character Lock component
// (parts_manifest.json), positioned/rotated by reading the corresponding
// bone's transform after each Armature::advanceTime() - the same
// "read bone->global, draw ourselves" technique, just with real traced
// artwork instead of placeholder shapes.
//
// No DragonBones source file is modified or copied; it is compiled directly
// from its existing location (see build.sh).

#include <cmath>
#include <cstdio>
#include <filesystem>
#include <fstream>
#include <sstream>
#include <string>
#include <vector>

#include <SFML/Graphics.hpp>
#include <rapidjson/document.h>

#include "PocRuntime.h"

using dragonBones::Armature;
using dragonBones::Bone;
using dragonBones::PocFactory;

namespace fs = std::filesystem;

static const float DEG2RAD = 3.14159265358979323846f / 180.0f;
static const float RAD2DEG = 180.0f / 3.14159265358979323846f;
static const float PI = 3.14159265358979323846f;

static std::string readFile(const std::string& path)
{
    std::ifstream file(path, std::ios::binary);
    if (!file) throw std::runtime_error("Could not open file: " + path);
    std::ostringstream ss;
    ss << file.rdbuf();
    return ss.str();
}

static float smoothstep(float x)
{
    x = std::max(0.0f, std::min(1.0f, x));
    return x * x * (3.0f - 2.0f * x);
}

// Same idle(0-5) / walk(6-17) / return(18-23) amplitude schedule as the
// proven DragonBonesCPP poc (main.cpp: walkAmplitude), landing on exactly
// amplitude 0 at both frame 0 and frame 23.
static float walkAmplitude(int frame)
{
    if (frame <= 5) return 0.0f;
    if (frame <= 17) return 1.0f;
    const float t2 = (frame - 17) / 6.0f;
    return 1.0f - smoothstep(t2);
}

struct Part
{
    std::string component;
    std::string boneName;
    std::string file;
    float pivotX = 0.f;
    float pivotY = 0.f;
    Bone* bone = nullptr;
    sf::Texture texture;
    sf::Sprite sprite;
};

int main()
{
    const int FPS = 24;
    const int FRAME_COUNT = 24;
    const float STRIDE_FREQ = 3.0f;

    fs::create_directories("output");

    // --- 1. Load the DragonBones skeleton generated from the Character Lock ---
    const std::string skeletonJson = readFile("character_ske.json");

    PocFactory factory;
    auto* data = factory.parseDragonBonesData(skeletonJson.c_str());
    if (data == nullptr)
    {
        std::fprintf(stderr, "Failed to parse character_ske.json\n");
        return 1;
    }

    Armature* armature = factory.buildArmature("Walker2");
    if (armature == nullptr)
    {
        std::fprintf(stderr, "Failed to build armature 'Walker2'\n");
        return 1;
    }

    // --- 2. Load parts_manifest.json (our own simple format, parsed with
    // rapidjson - already a DragonBones core dependency, so no new
    // third-party library is introduced) ---
    std::vector<Part> parts;
    {
        const std::string manifestJson = readFile("parts_manifest.json");
        rapidjson::Document doc;
        doc.Parse(manifestJson.c_str());
        if (doc.HasParseError() || !doc.HasMember("parts"))
        {
            std::fprintf(stderr, "Failed to parse parts_manifest.json\n");
            return 1;
        }
        for (const auto& p : doc["parts"].GetArray())
        {
            Part part;
            part.component = p["component"].GetString();
            part.boneName = p["bone"].GetString();
            part.file = p["file"].GetString();
            part.pivotX = static_cast<float>(p["pivot_x"].GetDouble());
            part.pivotY = static_cast<float>(p["pivot_y"].GetDouble());
            parts.push_back(std::move(part));
        }
    }

    float minX = 1e9f, minY = 1e9f, maxX = -1e9f, maxY = -1e9f;

    for (auto& part : parts)
    {
        part.bone = armature->getBone(part.boneName);
        if (part.bone == nullptr)
        {
            std::fprintf(stderr, "Unknown bone '%s' for part '%s'\n",
                part.boneName.c_str(), part.component.c_str());
            return 1;
        }
        if (!part.texture.loadFromFile(part.file))
        {
            std::fprintf(stderr, "Failed to load %s\n", part.file.c_str());
            return 1;
        }
        part.texture.setSmooth(true);
        part.sprite.setTexture(part.texture);
        part.sprite.setOrigin(part.pivotX, part.pivotY);

        // Track the rest-pose bounding extent (bone world position, ignoring
        // sprite size) purely to size the render canvas generously.
        part.bone->updateGlobalTransform();
        minX = std::min(minX, part.bone->global.x - 400.f);
        minY = std::min(minY, part.bone->global.y - 400.f);
        maxX = std::max(maxX, part.bone->global.x + 400.f);
        maxY = std::max(maxY, part.bone->global.y + 400.f);
    }

    const unsigned int WIDTH = static_cast<unsigned int>(maxX - minX);
    const unsigned int HEIGHT = static_cast<unsigned int>(maxY - minY);

    sf::RenderTexture renderTexture;
    if (!renderTexture.create(WIDTH, HEIGHT))
    {
        std::fprintf(stderr, "Failed to create off-screen RenderTexture (%ux%u)\n", WIDTH, HEIGHT);
        return 1;
    }
    sf::View view(sf::FloatRect(minX, minY, static_cast<float>(WIDTH), static_cast<float>(HEIGHT)));
    renderTexture.setView(view);

    Bone* root = armature->getBone("root");
    Bone* thigh_front = armature->getBone("thigh_front");
    Bone* shin_front = armature->getBone("shin_front");
    Bone* thigh_back = armature->getBone("thigh_back");
    Bone* shin_back = armature->getBone("shin_back");
    Bone* upper_arm_front = armature->getBone("upper_arm_front");
    Bone* forearm_front = armature->getBone("forearm_front");
    Bone* upper_arm_back = armature->getBone("upper_arm_back");
    Bone* forearm_back = armature->getBone("forearm_back");

    // --- 3. Deterministic 24-frame loop @ 24 FPS, t = frame / 24.0 ---
    for (int frame = 0; frame < FRAME_COUNT; ++frame)
    {
        const float t = static_cast<float>(frame) / static_cast<float>(FPS);
        const float A = walkAmplitude(frame);
        const float phase = 2.0f * PI * STRIDE_FREQ * t;

        // Pose DELTAS only (degrees) - rest orientation is already baked
        // into each bone's transform.skX/skY by the conversion script, and
        // "inheritRotation": false means DragonBones does not re-add the
        // parent's rotation, so writing just the delta here is correct and
        // keeps this frame-loop free of any hand-rolled FK math.
        //
        // IMPORTANT (documented seam fix - see POC report "visual
        // problems"): the *_front/_back leg and arm components are each a
        // SINGLE rigid raster image spanning the Character Lock's original
        // two-joint (thigh+shin / upper-arm+forearm) soft-skin contour -
        // this POC intentionally does not implement weighted mesh
        // deformation, so that single image cannot visually bend at the
        // knee/elbow. It is bound to the PROXIMAL bone only
        // (thigh_front/thigh_back/upper_arm_front/upper_arm_back). The
        // hand/foot parts are rigid_children bound to the DISTAL bone
        // (shin_*/forearm_*) per the lock's own attachment data. Giving the
        // distal bone its own independent rotation delta swings the
        // hand/foot away from the (non-bending) limb image, producing a
        // visible detachment at the ankle/wrist - reproduced and confirmed
        // during this POC. The distal bones are therefore kept at their
        // baked REST rotation (delta 0) here: the whole limb (image +
        // hand/foot) then rotates rigidly together from the proximal
        // joint only, which is the correct rigid-parts treatment of
        // geometry that was traced as one continuous two-joint contour.
        const float thighF = A * 30.f * std::sin(phase);
        const float thighB = A * 30.f * std::sin(phase + PI);

        const float upperArmF = A * 26.f * std::sin(phase + PI);
        const float upperArmB = A * 26.f * std::sin(phase);

        const float hipBounce = -A * 6.f * std::fabs(std::sin(phase));

        thigh_front->offset.rotation     = thighF * DEG2RAD;
        shin_front->offset.rotation      = 0.f;
        thigh_back->offset.rotation      = thighB * DEG2RAD;
        shin_back->offset.rotation       = 0.f;
        upper_arm_front->offset.rotation = upperArmF * DEG2RAD;
        forearm_front->offset.rotation   = 0.f;
        upper_arm_back->offset.rotation  = upperArmB * DEG2RAD;
        forearm_back->offset.rotation    = 0.f;
        root->offset.y                   = hipBounce;

        for (Bone* b : armature->getBones())
        {
            b->invalidUpdate();
        }

        armature->advanceTime(1.0f / FPS);

        // --- 4. Render this frame off-screen ---
        renderTexture.clear(sf::Color(235, 235, 230, 255));
        for (auto& part : parts)
        {
            part.bone->updateGlobalTransform();
            part.sprite.setPosition(part.bone->global.x, part.bone->global.y);
            // Pure pose delta, matching the rest-baked-into-origin design
            // (see comment above) - NOT bone->global.rotation, which would
            // double-count the rest orientation already visible in the art.
            part.sprite.setRotation(part.bone->offset.rotation * RAD2DEG);
            renderTexture.draw(part.sprite);
        }
        renderTexture.display();

        char filename[64];
        std::snprintf(filename, sizeof(filename), "output/frame_%04d.png", frame);
        sf::Image image = renderTexture.getTexture().copyToImage();
        if (!image.saveToFile(filename))
        {
            std::fprintf(stderr, "Failed to save %s\n", filename);
            return 1;
        }
        std::printf("wrote %s (t=%.4fs, phase=%s)\n", filename, t,
            frame <= 5 ? "idle" : (frame <= 17 ? "walk" : "return"));
    }

    armature->dispose();
    std::printf("Done: %d frames written to output/\n", FRAME_COUNT);
    return 0;
}
