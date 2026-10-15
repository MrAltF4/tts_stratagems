--[[
    40K Stratagem Bag Builder  (paste into TTS > Scripting > Global)

    One button. Click it and the script:
      1. downloads manifest.json from the GitHub repo
      2. builds a deck for every detachment from its _deck.png sheet
      3. nests them:  Faction bag > Detachment bag > Deck
      4. adds a Core Stratagems bag
      5. spawns the faction bags + core bag in a row on the table

    The ONLY line you need to edit is BASE_URL below.
    It must point at the repo's 11e folder and end with a slash.
]]

local BASE_URL = "https://raw.githubusercontent.com/YOUR_USER/YOUR_REPO/main/11e/"

-- ---------------------------------------------------------------------------
-- state
-- ---------------------------------------------------------------------------
local building    = false
local guidCounter = 0
local deckCounter = 0
local cardBackUrl = ""

local FACTION_COLOUR = { r = 0.15, g = 0.25, b = 0.20 }
local DET_COLOUR     = { r = 0.25, g = 0.40, b = 0.35 }
local CORE_COLOUR    = { r = 0.50, g = 0.50, b = 0.50 }

local BTN_COLORS     = "#0D2B40FF|#1A5C8AFF|#0A1F2EFF|#333333AA"
local BTN_TEXT_COLOR = "#3CCCFF"

-- forward declarations (per TTS gotchas: declare first, assign without `local`)
local setStatus

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
        FaceURL = BASE_URL .. group.deck.path,
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
    cardBackUrl = BASE_URL .. manifest.card_back
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
    setStatus("Spawned " .. #bagList .. " bags / " .. deckTotal .. " decks / " .. cardTotal .. " cards")
end

-- ---------------------------------------------------------------------------
-- entry points (global so XML onClick / chat can call them)
-- ---------------------------------------------------------------------------
function onBuildStratagems(player)
    if building then return end

    if string.find(BASE_URL, "YOUR_USER", 1, true) then
        setStatus("Edit BASE_URL at top of Global script first")
        return
    end

    building = true
    guidCounter = 0
    deckCounter = 0
    setStatus("Downloading manifest...")

    WebRequest.get(BASE_URL .. "manifest.json", function(request)
        if request.is_error then
            building = false
            setStatus("Download failed: " .. tostring(request.error))
            return
        end

        local ok, manifest = pcall(JSON.decode, request.text)
        if not ok or type(manifest) ~= "table" then
            building = false
            setStatus("manifest.json is not valid JSON")
            return
        end

        setStatus("Building bags...")
        local ok2, err = pcall(processManifest, manifest)
        building = false
        if not ok2 then
            setStatus("Build error: " .. tostring(err))
        end
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
