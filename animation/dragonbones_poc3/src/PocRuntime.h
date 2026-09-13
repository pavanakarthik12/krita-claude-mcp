// PocRuntime.h - POC #3
//
// Extends the same minimal-glue technique proven in
// DragonBonesCPP/poc/src/PocRuntime.h (POC #1/#2's PocFactory/PocArmatureProxy,
// copied here unchanged) with ONE new piece: a real Slot subclass
// (PocMeshSlot) that implements _updateMesh() - the one method DragonBones
// itself leaves to the host backend to implement (every backend, including
// the real SFML one at SFML/src/dragonBones/SFMLSlot.cpp, does the same
// thing). The algorithm in _updateMesh() below is copied verbatim from that
// real backend's SFMLSlot::_updateMesh() (linear blend skinning over the
// DeformVertices/VerticesData/WeightData the DragonBones CORE already
// parsed and tracks) - this is not a custom/approximate deformation, it is
// DragonBones' own documented weighted-skinning data format and the
// standard way every backend consumes it.
//
// No DragonBones source file is modified or copied wholesale; only this
// project's own glue code references its headers.

#pragma once

#include <dragonBones/DragonBonesHeaders.h>

DRAGONBONES_NAMESPACE_BEGIN

class PocTextureData : public TextureData
{
    BIND_CLASS_TYPE_B(PocTextureData);
public:
    PocTextureData() { _onClear(); }
    virtual ~PocTextureData() { _onClear(); }
};

class PocTextureAtlasData : public TextureAtlasData
{
    BIND_CLASS_TYPE_B(PocTextureAtlasData);
public:
    PocTextureAtlasData() {}
    TextureData* createTexture() const override
    {
        return BaseObject::borrowObject<PocTextureData>();
    }
};

class PocEventDispatcher : public IEventDispatcher
{
public:
    bool hasDBEventListener(const std::string&) const override { return false; }
    void dispatchDBEvent(const std::string&, EventObject*) override {}
    void addDBEventListener(const std::string&, const std::function<void(EventObject*)>&) override {}
    void removeDBEventListener(const std::string&, const std::function<void(EventObject*)>&) override {}
};

class PocArmatureProxy : public IArmatureProxy
{
public:
    Armature* armature = nullptr;
    PocEventDispatcher dispatcher;

    void dbInit(Armature* value) override { armature = value; }
    void dbClear() override { armature = nullptr; }
    void dbUpdate() override {}
    void dispose(bool /*disposeProxy*/) override {}

    Armature* getArmature() const override { return armature; }
    Animation* getAnimation() const override { return armature != nullptr ? armature->getAnimation() : nullptr; }

    bool hasDBEventListener(const std::string& type) const override { return dispatcher.hasDBEventListener(type); }
    void dispatchDBEvent(const std::string& type, EventObject* value) override { dispatcher.dispatchDBEvent(type, value); }
    void addDBEventListener(const std::string& type, const std::function<void(EventObject*)>& listener) override { dispatcher.addDBEventListener(type, listener); }
    void removeDBEventListener(const std::string& type, const std::function<void(EventObject*)>& listener) override { dispatcher.removeDBEventListener(type, listener); }
};

// A real mesh-capable Slot. Everything display/texture/z-order/color
// related is a no-op (this POC draws the deformed triangles itself, same
// "read the data, draw ourselves" approach as POC #1/#2's bone rectangles
// and sprites) - the one method that matters, _updateMesh(), is a faithful
// copy of the real backend's algorithm, reading the same DragonBones-parsed
// weight/bind data.
class PocMeshSlot : public Slot
{
    BIND_CLASS_TYPE_A(PocMeshSlot);

public:
    // World-space (x,y) pairs, one per mesh vertex, refreshed by
    // _updateMesh() every time DragonBones marks the deformation dirty
    // (bone moved, or first frame). main.cpp reads this directly.
    std::vector<float> deformedVertices;

protected:
    virtual void _onClear() override
    {
        Slot::_onClear();
        deformedVertices.clear();
    }

    virtual void _initDisplay(void*, bool) override {}
    virtual void _disposeDisplay(void*, bool) override {}
    virtual void _onUpdateDisplay() override {}
    virtual void _addDisplay() override {}
    virtual void _replaceDisplay(void*, bool) override {}
    virtual void _removeDisplay() override {}
    virtual void _updateZOrder() override {}
    virtual void _updateFrame() override {}
    virtual void _updateTransform() override {}
    virtual void _identityTransform() override {}

    // Verbatim port of SFMLSlot::_updateMesh() (SFML/src/dragonBones/SFMLSlot.cpp)
    // - standard DragonBones linear blend skinning: for each vertex, sum
    // over its influencing bones of (boneCurrentWorldMatrix * bindSpaceXY)
    // weighted by that bone's weight. The parser (JSONDataParser::_parseMesh)
    // already pre-multiplied each vertex by the INVERSE bind matrix at load
    // time, so this loop only needs each bone's CURRENT global matrix.
    virtual void _updateMesh() override
    {
        const auto scale = _armature->_armatureData->scale;
        const auto& deformVerts = _deformVertices->vertices; // FFD offsets - unused (empty) in this POC
        const auto& bones = _deformVertices->bones;
        const auto verticesData = _deformVertices->verticesData;
        const auto weightData = verticesData->weight;
        const auto hasFFD = !deformVerts.empty();

        if (weightData == nullptr)
        {
            return;
        }

        const auto data = verticesData->data;
        const auto& intArray = data->intArray;
        const auto& floatArray = data->floatArray;
        const auto vertexCount = (std::size_t)intArray[verticesData->offset + (unsigned)BinaryOffset::MeshVertexCount];
        int weightFloatOffset = intArray[weightData->offset + (unsigned)BinaryOffset::WeigthFloatOffset];
        if (weightFloatOffset < 0)
        {
            weightFloatOffset += 65536;
        }

        deformedVertices.assign(vertexCount * 2, 0.0f);

        for (
            std::size_t i = 0, iB = weightData->offset + (unsigned)BinaryOffset::WeigthBoneIndices + bones.size(), iV = (std::size_t)weightFloatOffset, iF = 0;
            i < vertexCount;
            ++i
        )
        {
            const auto boneCount = (std::size_t)intArray[iB++];
            float xG = 0.0f, yG = 0.0f;
            for (std::size_t j = 0; j < boneCount; ++j)
            {
                const auto boneIndex = (unsigned)intArray[iB++];
                const auto bone = bones[boneIndex];
                if (bone != nullptr)
                {
                    const auto& matrix = bone->globalTransformMatrix;
                    const auto weight = floatArray[iV++];
                    auto xL = floatArray[iV++] * scale;
                    auto yL = floatArray[iV++] * scale;

                    if (hasFFD)
                    {
                        xL += deformVerts[iF++];
                        yL += deformVerts[iF++];
                    }

                    xG += (matrix.a * xL + matrix.c * yL + matrix.tx) * weight;
                    yG += (matrix.b * xL + matrix.d * yL + matrix.ty) * weight;
                }
            }

            deformedVertices[i * 2] = xG;
            deformedVertices[i * 2 + 1] = yG;
        }
    }

public:
    virtual void _updateVisible() override {}
    virtual void _updateBlendMode() override {}
    virtual void _updateColor() override {}
};

class PocFactory : public BaseFactory
{
public:
    PocFactory() : BaseFactory(nullptr)
    {
        _dragonBones = new DragonBones(&_eventDispatcher);
    }

    ~PocFactory()
    {
        clear();
        delete _dragonBones;
    }

protected:
    TextureAtlasData* _buildTextureAtlasData(TextureAtlasData* textureAtlasData, void* /*textureAtlas*/) const override
    {
        if (textureAtlasData == nullptr)
        {
            return BaseObject::borrowObject<PocTextureAtlasData>();
        }
        return textureAtlasData;
    }

    Armature* _buildArmature(const BuildArmaturePackage& dataPackage) const override
    {
        const auto armature = BaseObject::borrowObject<Armature>();
        const auto proxy = new PocArmatureProxy();
        armature->init(dataPackage.armature, proxy, proxy, _dragonBones);
        return armature;
    }

    Slot* _buildSlot(const BuildArmaturePackage& /*dataPackage*/, const SlotData* slotData, Armature* armature) const override
    {
        const auto slot = BaseObject::borrowObject<PocMeshSlot>();
        slot->init(slotData, armature, slot, slot);
        return slot;
    }

private:
    PocEventDispatcher _eventDispatcher;
};

DRAGONBONES_NAMESPACE_END
