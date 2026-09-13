// main.cpp - the DragonBones adapter (target architecture step 15).
//
// This is intentionally "thin": it receives already-decided Pose data (as
// a baked JSON produced by animation/runtime/bake.py from the pure-Python
// CharacterAsset/CharacterInstance/Action/Sequencer/Scene layer) and does
// nothing except:
//   - load the CharacterAsset (the DragonBones armature/mesh/rigid-part
//     data generated once by POC #4's converter - reused unmodified here,
//     not regenerated)
//   - create one independent DragonBones Armature instance per character
//     (factory.buildArmature(), exactly as POC #4 proved)
//   - apply each frame's Pose (bone rotation deltas + translations) to
//     that instance's bones
//   - let DragonBones itself advance/evaluate (skinning, mesh deformation)
//   - render the result with the same proven headless SFML technique
//
// No bone-transform, skinning, or IK math is duplicated here - all of that
// remains inside the unmodified DragonBones C++ core (PocRuntime.h is
// copied verbatim from POC #4, itself a thin backend shim, not a
// reimplementation).

#include <cmath>
#include <cstdio>
#include <filesystem>
#include <fstream>
#include <map>
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

static std::string readFile(const std::string& path)
{
    std::ifstream file(path, std::ios::binary);
    if (!file) throw std::runtime_error("Could not open file: " + path);
    std::ostringstream ss;
    ss << file.rdbuf();
    return ss.str();
}

// ---------------------------------------------------------------------------
// CharacterAsset (same role as POC #4's): the parsed-once DragonBones data,
// reused as-is from animation/dragonbones_poc4's generated files. Nothing
// here re-derives geometry from the Character Lock - that conversion is
// POC #4's job and is not duplicated.
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

    bool load(const std::string& skeletonPath, const std::string& manifestPath, const std::string& partsBaseDir)
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
            const std::string texPath = partsBaseDir + "/" + part.component + ".png";
            if (!part.texture.loadFromFile(texPath))
            {
                std::fprintf(stderr, "Failed to load %s\n", texPath.c_str());
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
// CharacterInstance (DragonBonesCharacter, step 15's adapter object): owns
// one independent Armature and applies whatever Pose it is given each
// frame. Unlike POC #4, it does NOT decide what the pose should be -
// that decision was already made by the Python Action/Sequencer/Scene
// layer and handed to it as plain bone-name -> rotation-degrees /
// translation data (see applyPose below).
// ---------------------------------------------------------------------------
struct CharacterInstance
{
    CharacterAsset* asset = nullptr;
    Armature* armature = nullptr;
    std::vector<PocMeshSlot*> meshSlots;
    std::vector<Bone*> rigidBones;
    std::vector<sf::Sprite> rigidSprites;

    float worldX = 0.f, worldY = 0.f;
    float heading = 1.f;

    void init(CharacterAsset* a)
    {
        asset = a;
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

    void resetPose()
    {
        for (Bone* b : armature->getBones())
        {
            b->offset.rotation = 0.f;
            b->offset.x = 0.f;
            b->offset.y = 0.f;
        }
    }

    // The one method that matters for "receive Pose, apply bone
    // transforms" (requirement 15). boneRotationDeg/translations come
    // straight from Pose.bone_rotation_map() / Pose's per-bone
    // translations, serialized by bake.py - this function performs no
    // animation LOGIC of its own, only application.
    void applyPose(
        const std::map<std::string, float>& boneRotationDeg,
        const std::map<std::string, std::pair<float, float>>& translations,
        float x, float y, float headingIn)
    {
        resetPose();
        for (const auto& kv : boneRotationDeg)
        {
            Bone* b = armature->getBone(kv.first);
            if (b != nullptr) b->offset.rotation = kv.second * DEG2RAD;
        }
        for (const auto& kv : translations)
        {
            Bone* b = armature->getBone(kv.first);
            if (b != nullptr)
            {
                b->offset.x = kv.second.first;
                b->offset.y = kv.second.second;
            }
        }
        worldX = x;
        worldY = y;
        heading = headingIn;
    }

    void advance(float dt)
    {
        for (Bone* b : armature->getBones()) b->invalidUpdate();
        armature->advanceTime(dt);
        for (PocMeshSlot* slot : meshSlots)
        {
            if (slot != nullptr) slot->update(-1);
        }
    }

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

    void dumpState(std::ostream& out) const
    {
        out << "{";
        out << "\"worldX\":" << worldX << ",\"worldY\":" << worldY << ",\"heading\":" << heading << ",";
        out << "\"bones\":{";
        bool first = true;
        for (Bone* b : armature->getBones())
        {
            if (!first) out << ",";
            first = false;
            out << "\"" << b->getName() << "\":" << (b->offset.rotation * RAD2DEG);
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

int main(int argc, char** argv)
{
    const std::string bakedPath = argc > 1 ? argv[1] : "test_output/baked_scene.json";
    const std::string outDir = argc > 2 ? argv[2] : "test_output";

    fs::create_directories(outDir);
    fs::create_directories(outDir + "/dump");

    // Phase 2B note: DragonBones' native IK constraint system was tried
    // here (see build_ik_skeleton.py / ik_probe.py) and empirically found
    // incompatible with this asset's "inheritRotation: false" leg bones
    // (POC #2's deliberate convention so pose code can write pure rotation
    // DELTAS without hand-composing FK) - IKConstraint::_computeB assumes
    // standard rotation INHERITANCE down the thigh->shin chain, and with
    // it disabled the solve produced a visibly contorted leg even at the
    // target's own rest position. Reworking the whole skeleton's rotation
    // convention to satisfy the native IK constraint was out of scope for
    // this phase's time budget, so foot-contact IK is computed instead as
    // a standard closed-form 2-bone (law of cosines) solve in the Python
    // action layer (see actions/walk.py's _solve_2bone_ik) and applied
    // through this exact same, unmodified bone-rotation pipeline - see the
    // final report for the full account. This adapter therefore still
    // loads POC #4's plain, unmodified skeleton.
    const std::string skePath = argc > 3 ? argv[3] : "../dragonbones_poc4/character_ske.json";
    CharacterAsset asset;
    if (!asset.load(
            skePath,
            "../dragonbones_poc4/parts_manifest.json",
            "../dragonbones_poc4/parts"))
    {
        return 1;
    }
    std::printf("Loaded asset: %zu mesh slots, %zu rigid parts\n", asset.meshes.size(), asset.rigidParts.size());

    const std::string bakedJsonText = readFile(bakedPath);
    rapidjson::Document baked;
    baked.Parse(bakedJsonText.c_str());
    if (baked.HasParseError())
    {
        std::fprintf(stderr, "Failed to parse %s\n", bakedPath.c_str());
        return 1;
    }

    const unsigned WIDTH = baked["width"].GetUint();
    const unsigned HEIGHT = baked["height"].GetUint();
    const int fps = baked["fps"].GetInt();
    const int frameCount = baked["frameCount"].GetInt();
    const float camX = static_cast<float>(baked["camera"]["x"].GetDouble());
    const float camY = static_cast<float>(baked["camera"]["y"].GetDouble());
    const float camZoom = static_cast<float>(baked["camera"]["zoom"].GetDouble());

    std::vector<std::string> characterIds;
    for (const auto& id : baked["characterIds"].GetArray())
    {
        characterIds.push_back(id.GetString());
    }

    std::map<std::string, CharacterInstance> characters;
    for (const auto& id : characterIds)
    {
        characters[id].init(&asset);
    }

    sf::RenderTexture renderTexture;
    if (!renderTexture.create(WIDTH, HEIGHT))
    {
        std::fprintf(stderr, "Failed to create %ux%u RenderTexture\n", WIDTH, HEIGHT);
        return 1;
    }
    const float viewWidth = static_cast<float>(WIDTH) / camZoom;
    const float viewHeight = static_cast<float>(HEIGHT) / camZoom;
    sf::View view(sf::FloatRect(camX - viewWidth / 2.f, camY - viewHeight / 2.f, viewWidth, viewHeight));
    renderTexture.setView(view);

    const auto& frames = baked["frames"];
    for (int frame = 0; frame < frameCount; ++frame)
    {
        const auto& frameJson = frames[frame];

        for (const auto& id : characterIds)
        {
            const auto& charJson = frameJson[id.c_str()];

            std::map<std::string, float> boneRotationDeg;
            for (auto it = charJson["boneRotationDeg"].MemberBegin(); it != charJson["boneRotationDeg"].MemberEnd(); ++it)
            {
                boneRotationDeg[it->name.GetString()] = static_cast<float>(it->value.GetDouble());
            }

            std::map<std::string, std::pair<float, float>> translations;
            for (auto it = charJson["translations"].MemberBegin(); it != charJson["translations"].MemberEnd(); ++it)
            {
                const auto& arr = it->value;
                translations[it->name.GetString()] = {
                    static_cast<float>(arr[0].GetDouble()),
                    static_cast<float>(arr[1].GetDouble())
                };
            }

            const float x = static_cast<float>(charJson["x"].GetDouble());
            const float y = static_cast<float>(charJson["y"].GetDouble());
            const float heading = static_cast<float>(charJson["heading"].GetDouble());

            CharacterInstance& inst = characters[id];
            inst.applyPose(boneRotationDeg, translations, x, y, heading);
            inst.advance(1.0f / static_cast<float>(fps));
        }

        renderTexture.clear(sf::Color(235, 235, 230, 255));
        for (const auto& id : characterIds)
        {
            characters[id].draw(renderTexture);
        }
        renderTexture.display();

        char filename[256];
        std::snprintf(filename, sizeof(filename), "%s/frame_%04d.png", outDir.c_str(), frame);
        sf::Image image = renderTexture.getTexture().copyToImage();
        if (!image.saveToFile(filename))
        {
            std::fprintf(stderr, "Failed to save %s\n", filename);
            return 1;
        }

        char dumpFilename[256];
        std::snprintf(dumpFilename, sizeof(dumpFilename), "%s/dump/frame_%04d.json", outDir.c_str(), frame);
        std::ofstream dumpOut(dumpFilename);
        dumpOut << "{";
        bool first = true;
        for (const auto& id : characterIds)
        {
            if (!first) dumpOut << ",";
            first = false;
            dumpOut << "\"" << id << "\":";
            characters[id].dumpState(dumpOut);
        }
        dumpOut << "}";

        std::printf("wrote %s\n", filename);
    }

    for (const auto& id : characterIds) characters[id].armature->dispose();
    std::printf("Done: %d frames written to %s/\n", frameCount, outDir.c_str());
    return 0;
}
