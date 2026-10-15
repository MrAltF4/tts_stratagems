--[[
    40K Stratagem Bag Builder  (paste into TTS > Scripting > Global)

    One button. Click it and the script:
      1. downloads latest.json to find the current release folder (e.g. v0.1)
      2. downloads that release's manifest.json
      3. builds a deck for every detachment from its _deck.png sheet
      4. nests them:  Faction bag > Detachment bag > Deck
      5. adds a Core Stratagems bag
      6. spawns the faction bags + core bag in a row on the table

    The ONLY line you need to edit is ROOT_URL below.
    It must point at the repo's 11e-stratagems folder (the one holding latest.json)
    and end with a slash. New releases are picked up from latest.json automatically.
]]

local ROOT_URL = "https://raw.githubusercontent.com/MrAltF4/tts_stratagems/main/11e-stratagems/"

-- ---------------------------------------------------------------------------
-- state
-- ---------------------------------------------------------------------------
local BASE_URL    = ""   -- ROOT_URL .. "<version>/", set from latest.json on each build
local version     = ""
local building    = false
local guidCounter = 0
local deckCounter = 0
local cardBackUrl = ""
local assetBuild  = ""   -- from manifest; appended to image URLs so TTS never reuses a stale cached image

local FACTION_COLOUR = { r = 0.15, g = 0.25, b = 0.20 }
local DET_COLOUR     = { r = 0.25, g = 0.40, b = 0.35 }
local CORE_COLOUR    = { r = 0.50, g = 0.50, b = 0.50 }

local BTN_COLORS     = "#0D2B40FF|#1A5C8AFF|#0A1F2EFF|#333333AA"
local BTN_TEXT_COLOR = "#3CCCFF"

-- forward declarations (per TTS gotchas: declare first, assign without `local`)
local setStatus

local function assetUrl(path)
    if assetBuild ~= "" then
        return BASE_URL .. path .. "?v=" .. assetBuild
    end
    return BASE_URL .. path
end

-- ---------------------------------------------------------------------------
-- UI (Global UI, always present - XML built with table.insert)
-- ---------------------------------------------------------------------------
local function buildUiXml()
    local lines = {}
    table.insert(lines, '<Panel id="strat_panel" rectAlignment="UpperLeft" offsetXY="20 -20" width="260" height="92" color="#101820E6">')
    table.insert(lines, '  <Button id="strat_btn" onClick="onBuildStratagems" rectAlignment="UpperLeft" offsetXY="10 -10" width="240" height="40" fontSize="16" colors="' .. BTN_COLORS .. '" transition="ColorTint">')
    table.insert(lines, '    <Text id="strat_btn_text" text="Build Stratagem Bags" color="' .. BTN_TEXT_COLOR .. '" fontSize="16" width="240" height="40" alignment="MiddleCenter" />')
    table.insert(lines, '  </Button>')
    table.insert(lines, '  <Text id="strat_status" text="Ready" color="#FFFFFF" fontSize="12" rectAlignment="UpperLeft" offsetXY="10 -56" width="240" height="30" alignment="MiddleLeft" />')
    table.insert(lines, '</Panel>')
    return table.concat(lines, "\n")
end

setStatus = function(text)
    UI.setAttribute("strat_status", "text", text)
    print("[Stratagems] " .. text)
end

-- ---------------------------------------------------------------------------
-- object-data builders (same structure as TTS saved-object JSON)
-- ---------------------------------------------------------------------------
local function nextGuid()
    guidCounter = guidCounter + 1
    return string.format("%06x", 10485760 + guidCounter)   -- 0xA00000 + n
end

local function makeTransform(rotY, rotZ)
    return {
        posX = 0, posY = 1, posZ = 0,
        rotX = 0, rotY = rotY or 180, rotZ = rotZ or 0,
        scaleX = 1, scaleY = 1, scaleZ = 1,
    }
end

local function baseObject(name, nickname, transform, colour)
    return {
        GUID = nextGuid(),
        Name = name,
        Nickname = nickname,
        Transform = transform,
        Description = "",
        GMNotes = "",
        ColorDiffuse = colour or { r = 0.7, g = 0.7, b = 0.7 },
        Locked = false,
        Grid = true,
        Snap = true,
        Autoraise = true,
        Sticky = true,
        Tooltip = true,
        GridProjection = false,
        HideWhenFaceDown = false,
        Hands = false,
        LuaScript = "",
        LuaScriptState = "",
        XmlUI = "",
    }
end

-- group = a detachment (or the core group) from the manifest: { cards = {...}, deck = {...} }
local function makeDeck(group, nickname)
    deckCounter = deckCounter + 1
    local key = deckCounter

    local customDeck = {}
    customDeck[tostring(key)] = {
        FaceURL = assetUrl(group.deck.path),
        BackURL = cardBackUrl,
        NumWidth = group.deck.cols,
        NumHeight = group.deck.rows,
        BackIsHidden = true,
        UniqueBack = false,
        Type = 0,
    }

    local cards = {}
    local ids = {}
    for _, c in ipairs(group.cards) do
        local cardId = key * 100 + c.deck_index
        local card = baseObject("Card", c.name, makeTransform(180, 180))
        card.CardID = cardId
        card.SidewaysCard = false
        card.CustomDeck = customDeck
        card.HideWhenFaceDown = true
        card.Hands = true
        table.insert(cards, card)
        table.insert(ids, cardId)
    end

    local deck = baseObject("DeckCustom", nickname, makeTransform(180, 180))
    deck.DeckIDs = ids
    deck.CustomDeck = customDeck
    deck.SidewaysCard = false
    deck.HideWhenFaceDown = true
    deck.ContainedObjects = cards
    return deck
end

local function makeBag(nickname, colour, contents)
    local bag = baseObject("Bag", nickname, makeTransform(0, 0), colour)
    bag.ContainedObjects = contents
    return bag
end

local function buildFactionBag(faction)
    local detachmentBags = {}
    for _, det in ipairs(faction.detachments) do
        local deck = makeDeck(det, det.name .. " Stratagems")
        table.insert(detachmentBags, makeBag(det.name, DET_COLOUR, { deck }))
    end
    return makeBag(faction.name .. " - Stratagems", FACTION_COLOUR, detachmentBags)
end

-- ---------------------------------------------------------------------------
-- spawning
-- ---------------------------------------------------------------------------
local function spawnAll(bagList)
    local spacing = 4
    local startX = -((#bagList - 1) * spacing) / 2
    for i, bagData in ipairs(bagList) do
        -- stagger so TTS doesn't hitch on one giant frame
        Wait.time(function()
            spawnObjectData({
                data = bagData,
                position = { x = startX + (i - 1) * spacing, y = 2, z = 0 },
                rotation = { x = 0, y = 0, z = 0 },
            })
        end, (i - 1) * 0.4)
    end
end

local function processManifest(manifest)
    assetBuild = tostring(manifest.build or "")
    cardBackUrl = assetUrl(manifest.card_back)
    local bagList = {}
    local deckTotal, cardTotal = 0, 0

    for _, faction in ipairs(manifest.factions or {}) do
        table.insert(bagList, buildFactionBag(faction))
        for _, det in ipairs(faction.detachments) do
            deckTotal = deckTotal + 1
            cardTotal = cardTotal + #det.cards
        end
    end

    if manifest.core then
        local deck = makeDeck(manifest.core, "Core Stratagems")
        table.insert(bagList, makeBag("Core Stratagems", CORE_COLOUR, { deck }))
        deckTotal = deckTotal + 1
        cardTotal = cardTotal + #manifest.core.cards
    end

    spawnAll(bagList)
    setStatus(version .. ": spawned " .. #bagList .. " bags / " .. deckTotal .. " decks / " .. cardTotal .. " cards")
end

-- download a URL and decode it as JSON; onDone(data) on success, otherwise sets status and stops the build
local function fetchJson(url, label, onDone)
    WebRequest.get(url, function(request)
        if request.is_error then
            building = false
            setStatus(label .. " download failed: " .. tostring(request.error))
            return
        end

        local ok, data = pcall(JSON.decode, request.text)
        if not ok or type(data) ~= "table" then
            building = false
            setStatus(label .. " is not valid JSON")
            return
        end

        onDone(data)
    end)
end

-- ---------------------------------------------------------------------------
-- entry points (global so XML onClick / chat can call them)
-- ---------------------------------------------------------------------------
function onBuildStratagems(player)
    if building then return end

    if string.find(ROOT_URL, "YOUR_USER", 1, true) then
        setStatus("Edit ROOT_URL at top of Global script first")
        return
    end

    building = true
    guidCounter = 0
    deckCounter = 0
    setStatus("Finding latest release...")

    fetchJson(ROOT_URL .. "latest.json", "latest.json", function(latest)
        -- folder name only, e.g. "v0.1" (letters, digits, dot, dash, underscore)
        local v = tostring(latest.version or "")
        if not string.match(v, "^[%w%.%-_]+$") then
            building = false
            setStatus("latest.json has no valid version")
            return
        end
        version  = v
        BASE_URL = ROOT_URL .. version .. "/"
        setStatus("Downloading " .. version .. " manifest...")

        fetchJson(BASE_URL .. "manifest.json", "manifest.json", function(manifest)
            setStatus("Building " .. version .. " bags...")
            local ok, err = pcall(processManifest, manifest)
            building = false
            if not ok then
                setStatus("Build error: " .. tostring(err))
            end
        end)
    end)
end

-- fallback if the button ever misbehaves: type  !stratagems  in chat
function onChat(message, player)
    if message == "!stratagems" then
        onBuildStratagems(player)
        return false
    end
end

function onLoad()
    UI.setXml(buildUiXml())
end
