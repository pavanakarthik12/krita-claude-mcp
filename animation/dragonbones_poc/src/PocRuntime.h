// PocRuntime.h
//
// Minimal glue between the unmodified DragonBones C++ core
// (../../DragonBones/src/dragonBones) and this proof-of-concept.
//
// This file does NOT touch or copy any DragonBones source. It only
// implements the two abstract interfaces the core requires from any
// host engine:
//   - IArmatureProxy  (armature/IArmatureProxy.h)
//   - IEventDispatcher (event/IEventDispatcher.h), via BaseFactory hooks
//
// Every method here is a no-op stub. That is deliberate: the goal of
// this POC is to prove the DragonBones core (Armature/Bone/Transform)
// works completely headless, with no display/texture system attached.
// Rendering is done separately in main.cpp by reading bone->global
// after each Armature::advanceTime() call.

#pragma once

#include <dragonBones/DragonBonesHeaders.h>

DRAGONBONES_NAMESPACE_BEGIN

// Minimal concrete TextureData/TextureAtlasData. This POC never draws
// a textured slot (the skeleton has zero slots), but BaseFactory's
// generic parseDragonBonesData() flow unconditionally probes for an
// embedded texture atlas via _buildTextureAtlasData(nullptr, nullptr)
// before it even looks at the skeleton content, so a real (if inert)
// implementation of these two abstract classes is still required.
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

// A no-op event dispatcher: this POC drives bones directly and never
// needs DragonBones' own event system (animation-complete events, etc).
class PocEventDispatcher : public IEventDispatcher
{
public:
    bool hasDBEventListener(const std::string&) const override { return false; }
    void dispatchDBEvent(const std::string&, EventObject*) override {}
    void addDBEventListener(const std::string&, const std::function<void(EventObject*)>&) override {}
    void removeDBEventListener(const std::string&, const std::function<void(EventObject*)>&) override {}
};

// A no-op armature display proxy. Real backends (SFMLArmatureProxy,
// CCArmatureDisplay, ...) use this hook to sync a renderable node's
// transform/slots every time the armature updates (dbUpdate). This POC
// does not need that: we read bone transforms straight from the
// Armature object right after advanceTime(), so dbUpdate() does nothing.
class PocArmatureProxy : public IArmatureProxy
{
public:
    Armature* armature = nullptr;
    PocEventDispatcher dispatcher;

    void dbInit(Armature* value) override { armature = value; }
    void dbClear() override { armature = nullptr; }
    void dbUpdate() override { /* no display to sync - headless */ }
    void dispose(bool /*disposeProxy*/) override { /* armature is destroyed by BaseFactory::clear() */ }

    Armature* getArmature() const override { return armature; }
    Animation* getAnimation() const override { return armature != nullptr ? armature->getAnimation() : nullptr; }

    bool hasDBEventListener(const std::string& type) const override { return dispatcher.hasDBEventListener(type); }
    void dispatchDBEvent(const std::string& type, EventObject* value) override { dispatcher.dispatchDBEvent(type, value); }
    void addDBEventListener(const std::string& type, const std::function<void(EventObject*)>& listener) override { dispatcher.addDBEventListener(type, listener); }
    void removeDBEventListener(const std::string& type, const std::function<void(EventObject*)>& listener) override { dispatcher.removeDBEventListener(type, listener); }
};

// Minimal BaseFactory implementation. We never build slots or texture
// atlases (the skeleton JSON has an empty "skin" list), so those two
// overrides are unreachable in practice and simply assert if that
// assumption is ever violated.
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
        // Mirrors the pattern used by every real backend (e.g. SFMLFactory):
        // called with nullptr during parseDragonBonesData()'s generic
        // "is there an embedded atlas?" probe - just hand back an empty one.
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

    Slot* _buildSlot(const BuildArmaturePackage& /*dataPackage*/, const SlotData* /*slotData*/, Armature* /*armature*/) const override
    {
        DRAGONBONES_ASSERT(false, "POC skeleton has no slots.");
        return nullptr;
    }

private:
    PocEventDispatcher _eventDispatcher;
};

DRAGONBONES_NAMESPACE_END
