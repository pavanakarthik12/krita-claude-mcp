// main.cpp - POC #3: real DragonBones weighted-mesh skinning for the
// walker2 Character Lock's traced front leg (thigh -> shin), proving it
// solves POC #2's "rigid part freezes the distal bone" problem.
//
// Same architecture as POC #1/#2 (unmodified DragonBones C++ core,
// deterministic explicit frame stepping, headless SFML rendering to PNG),
// with ONE new piece: the leg is a REAL DragonBones mesh+skin display
// (character_ske.json's "skin"/"slot"/mesh data), and its per-vertex
// deformation is computed by DragonBones' own weighted-skinning data
// (read via PocMeshSlot::_updateMesh(), see PocRuntime.h) - not faked here.
// The foot remains a rigid sprite (same technique as POC #2), matching the
// Character Lock's own attachment data (front_foot is a rigid_child, not
// part of the soft-skin blend).

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
using dragonBones::PocMeshSlot;

namespace fs = std::filesystem;

static const float DEG2RAD = 3.14159265358979323846f / 180.0f;

static std::string readFile(const std::string& path)
{
    std::ifstream file(path, std::ios::binary);
    if (!file) throw std::runtime_error("Could not open file: " + path);
    std::ostringstream ss;
    ss << file.rdbuf();
    return ss.str();
}

struct FootPart
{
    std::string bone;
    float pivotX = 0.f, pivotY = 0.f;
    sf::Texture texture;
    sf::Sprite sprite;
};

int main()
{
    fs::create_directories("output/poses");
    fs::create_directories("output/sequence");

    // --- Load the generated mesh-bearing skeleton ---
    const std::string skeletonJson = readFile("character_ske.json");
    PocFactory factory;
    auto* data = factory.parseDragonBonesData(skeletonJson.c_str());
    if (data == nullptr) { std::fprintf(stderr, "Failed to parse character_ske.json\n"); return 1; }

    Armature* armature = factory.buildArmature("Limb");
    if (armature == nullptr) { std::fprintf(stderr, "Failed to build armature 'Limb'\n"); return 1; }

    Bone* thigh = armature->getBone("thigh");
    Bone* shin = armature->getBone("shin");
    if (thigh == nullptr || shin == nullptr) { std::fprintf(stderr, "Missing thigh/shin bone\n"); return 1; }

    auto* legSlot = dynamic_cast<PocMeshSlot*>(armature->getSlot("front_leg"));
    if (legSlot == nullptr) { std::fprintf(stderr, "Missing 'front_leg' mesh slot\n"); return 1; }

    // --- Re-read the triangle index list directly (same source file the
    // converter wrote; main.cpp needs it to build the SFML vertex array) ---
    std::vector<unsigned> triangleIndices;
    {
        rapidjson::Document doc;
        doc.Parse(skeletonJson.c_str());
        const auto& mesh = doc["armature"][0]["skin"][0]["slot"][0]["display"][0];
        for (const auto& v : mesh["triangles"].GetArray())
        {
            triangleIndices.push_back(v.GetUint());
        }
    }

    // --- Load the rigid foot part (POC #2 technique, reused unchanged) ---
    FootPart foot;
    {
        const std::string manifestJson = readFile("parts_manifest.json");
        rapidjson::Document doc;
        doc.Parse(manifestJson.c_str());
        const auto& p = doc["parts"][0];
        foot.bone = p["bone"].GetString();
        foot.pivotX = static_cast<float>(p["pivot_x"].GetDouble());
        foot.pivotY = static_cast<float>(p["pivot_y"].GetDouble());
        if (!foot.texture.loadFromFile(p["file"].GetString()))
        {
            std::fprintf(stderr, "Failed to load foot texture\n");
            return 1;
        }
        foot.texture.setSmooth(true);
        foot.sprite.setTexture(foot.texture);
        foot.sprite.setOrigin(foot.pivotX, foot.pivotY);
    }
    Bone* footBone = armature->getBone(foot.bone);

    // --- Canvas sized generously around the leg's rest position ---
    thigh->updateGlobalTransform();
    const float cx = thigh->global.x;
    const float cy = thigh->global.y;
    const unsigned int WIDTH = 700;
    const unsigned int HEIGHT = 700;
    const float minX = cx - 350.f;
    const float minY = cy - 60.f; // hip near the top of frame; leg+foot extend downward

    sf::RenderTexture renderTexture;
    if (!renderTexture.create(WIDTH, HEIGHT)) { std::fprintf(stderr, "Failed to create RenderTexture\n"); return 1; }
    sf::View view(sf::FloatRect(minX, minY, static_cast<float>(WIDTH), static_cast<float>(HEIGHT)));
    renderTexture.setView(view);

    auto renderFrame = [&](const std::string& path, float shinDeltaDeg) -> bool
    {
        thigh->offset.rotation = 0.0f; // hip/thigh stays stable - requirement 7
        shin->offset.rotation = shinDeltaDeg * DEG2RAD;

        for (Bone* b : armature->getBones()) b->invalidUpdate();
        armature->advanceTime(1.0f / 24.0f);

        // Force this slot's own update (mirrors what Armature::advanceTime's
        // internal slot pass does) so deformedVertices is current even
        // though this POC calls advanceTime() once per still pose rather
        // than as part of a running clock.
        legSlot->update(-1);

        sf::VertexArray tris(sf::Triangles, triangleIndices.size());
        const auto& verts = legSlot->deformedVertices;
        for (std::size_t i = 0; i < triangleIndices.size(); ++i)
        {
            const auto idx = triangleIndices[i];
            const float x = verts[idx * 2];
            const float y = verts[idx * 2 + 1];
            tris[i].position = sf::Vector2f(x, y);
            // Shade by (approximate) knee-relative depth for visual clarity
            // only - color has no bearing on the deformation being tested.
            tris[i].color = sf::Color(110, 140, 190, 255);
        }

        renderTexture.clear(sf::Color(235, 235, 230, 255));
        renderTexture.draw(tris);

        if (footBone != nullptr)
        {
            footBone->updateGlobalTransform();
            foot.sprite.setPosition(footBone->global.x, footBone->global.y);
            foot.sprite.setRotation(footBone->offset.rotation * 180.0f / 3.14159265358979323846f);
            renderTexture.draw(foot.sprite);
        }

        renderTexture.display();
        sf::Image image = renderTexture.getTexture().copyToImage();
        if (!image.saveToFile(path))
        {
            std::fprintf(stderr, "Failed to save %s\n", path.c_str());
            return false;
        }
        std::printf("wrote %s (shin delta = %.1f deg)\n", path.c_str(), shinDeltaDeg);
        return true;
    };

    // Requirement 10 ("rest pose matches the original Character Lock
    // rasterization", "zero-angle pose has no unintended displacement"):
    // dump the actual DragonBones-computed deformed vertex positions at
    // shin delta = 0 so verify.py can numerically diff them against the
    // converter's own source vertex list, rather than relying on visual
    // inspection alone.
    auto dumpVertices = [&](const std::string& path)
    {
        std::ofstream out(path);
        out << "[";
        const auto& verts = legSlot->deformedVertices;
        for (std::size_t i = 0; i < verts.size(); i += 2)
        {
            if (i > 0) out << ",";
            out << "[" << verts[i] << "," << verts[i + 1] << "]";
        }
        out << "]";
    };

    // --- Requirement 7: four discrete test poses ---
    const float poses[] = {0.0f, 15.0f, 30.0f, 45.0f};
    const char* poseNames[] = {"pose_000", "pose_015", "pose_030", "pose_045"};
    for (int i = 0; i < 4; ++i)
    {
        if (!renderFrame("output/poses/" + std::string(poseNames[i]) + ".png", poses[i])) return 1;
        dumpVertices("output/poses/" + std::string(poseNames[i]) + "_vertices.json");
    }

    // --- Requirement 7: continuous sequence 0->15->30->45->30->15->0 ---
    // 24 frames, triangular wave, deterministic t = frame/24 (no wall clock).
    const int SEQ_FRAMES = 25;
    for (int frame = 0; frame < SEQ_FRAMES; ++frame)
    {
        const float t = static_cast<float>(frame) / (SEQ_FRAMES - 1); // 0..1
        // Triangular wave: 0 -> 1 -> 0 over t in [0,1], peaking at t=0.5.
        const float tri = (t <= 0.5f) ? (t * 2.0f) : (2.0f - t * 2.0f);
        const float shinDelta = tri * 45.0f;

        char filename[64];
        std::snprintf(filename, sizeof(filename), "output/sequence/seq_%04d.png", frame);
        if (!renderFrame(filename, shinDelta)) return 1;
    }

    armature->dispose();
    std::printf("Done: 4 pose frames + %d sequence frames written to output/\n", SEQ_FRAMES);
    return 0;
}
