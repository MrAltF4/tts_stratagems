--[[
    40K Stratagem Bag Builder  (paste into TTS > Scripting > Global)

    On load the panel downloads versions.json and fills the Version dropdown
    (latest release preselected). Pick a version, click the button, and the script:
      1. downloads that release's manifest.json
      2. builds a deck for every detachment from its _deck.png sheet
      3. nests them:  Faction bag > Detachment bag > Deck
      4. adds a Core Stratagems bag
      5. puts them all in one master bag ("40K Stratagems - 11e <version>") and spawns it
         at SPAWN_POSITION, ready to be saved as a single object for another mod

    The ONLY line you need to edit is ROOT_URL below.
    It must point at the repo's 11e-stratagems folder (the one holding versions.json)
    and end with a slash. New releases are picked up from versions.json automatically.
	
	==========================================================================================================================
	========= Created by MrAltF4 =============================================================================================
	==========================================================================================================================
	=============================== Not possible without the support from https://game-datacards.eu/ =========================
]]

local ROOT_URL = "https://raw.githubusercontent.com/MrAltF4/tts_stratagems/main/11e-stratagems/"

-- ---------------------------------------------------------------------------
-- state
-- ---------------------------------------------------------------------------
local BASE_URL    = ""   -- ROOT_URL .. "<version>/", set when a build starts
local version     = ""   -- version being built

local versions        = {}   -- folder names from versions.json, in file order (newest first)
local latestVersion   = ""
local selectedVersion = ""   -- what the dropdown currently shows
local versionsLoaded  = false
local loadingVersions = false

local building    = false
local guidCounter = 0
local deckCounter = 0
local cardBackUrl = ""
local assetBuild  = ""   -- from manifest; appended to image URLs so TTS never reuses a stale cached image

local FACTION_COLOUR = { r = 0.15, g = 0.25, b = 0.20 }
local DET_COLOUR     = { r = 0.25, g = 0.40, b = 0.35 }
local CORE_COLOUR    = { r = 0.50, g = 0.50, b = 0.50 }
local MASTER_COLOUR  = { r = 0.60, g = 0.10, b = 0.10 }

local SPAWN_POSITION = { x = 0, y = 3, z = 0 }   -- where the master bag appears (table centre)

local BTN_COLORS     = "#0D2B40FF|#1A5C8AFF|#0A1F2EFF|#333333AA"
local BTN_TEXT_COLOR = "#3CCCFF"

-- forward declarations (per TTS gotchas: declare first, assign without `local`)
local setStatus
local loadVersions

-- folder name only, e.g. "v0.1" (letters, digits, dot, dash, underscore); also keeps it XML-safe
local function isValidVersion(v)
    return type(v) == "string" and string.match(v, "^[%w%.%-_]+$") ~= nil
end

-- status text can include web error messages; keep them from breaking the XML
local function xmlEscape(s)
    return (tostring(s):gsub("&", "&amp;"):gsub("<", "&lt;"):gsub(">", "&gt;"):gsub('"', "&quot;"))
end

local function hasVersion(v)
    for _, known in ipairs(versions) do
        if known == v then return true end
    end
    return false
end

local function assetUrl(path)
    if assetBuild ~= "" then
        return BASE_URL .. path .. "?v=" .. assetBuild
    end
    return BASE_URL .. path
end

-- ---------------------------------------------------------------------------
-- UI (Global UI, always present - XML built with table.insert)
-- ---------------------------------------------------------------------------
-- Rebuilt whenever the version list changes (structural change: the dropdown options).
-- statusText is baked in because setAttribute straight after setXml can be lost while the UI reloads.
local function buildUiXml(statusText)
    local btnLabel = versionsLoaded and "Build Stratagem Bags" or "Reload Versions"

    local lines = {}
    table.insert(lines, '<Panel id="strat_panel" rectAlignment="UpperCenter" offsetXY="0 -150" width="260" height="130" color="#101820E6">')
    table.insert(lines, '  <Text text="Version" color="#FFFFFF" fontSize="14" rectAlignment="UpperLeft" offsetXY="10 -10" width="70" height="30" alignment="MiddleLeft" />')
    table.insert(lines, '  <Dropdown id="strat_version" onValueChanged="onVersionChosen" rectAlignment="UpperLeft" offsetXY="80 -10" width="170" height="30" fontSize="14">')
    if #versions == 0 then
        table.insert(lines, '    <Option selected="true">' .. (loadingVersions and "Loading..." or "None found") .. '</Option>')
    else
        for _, v in ipairs(versions) do
            local label = v
            if v == latestVersion then label = v .. " (latest)" end
            local selected = (v == selectedVersion) and ' selected="true"' or ''
            table.insert(lines, '    <Option' .. selected .. '>' .. label .. '</Option>')
        end
    end
    table.insert(lines, '  </Dropdown>')
    table.insert(lines, '  <Button id="strat_btn" onClick="onBuildStratagems" rectAlignment="UpperLeft" offsetXY="10 -48" width="240" height="40" fontSize="16" colors="' .. BTN_COLORS .. '" transition="ColorTint">')
    table.insert(lines, '    <Text id="strat_btn_text" text="' .. btnLabel .. '" color="' .. BTN_TEXT_COLOR .. '" fontSize="16" width="240" height="40" alignment="MiddleCenter" />')
    table.insert(lines, '  </Button>')
    table.insert(lines, '  <Text id="strat_status" text="' .. xmlEscape(statusText or "") .. '" color="#FFFFFF" fontSize="12" rectAlignment="UpperLeft" offsetXY="10 -94" width="240" height="30" alignment="MiddleLeft" />')
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

    -- a TTS deck needs at least 2 cards; a 1-card detachment goes in its bag as a plain card
    if #cards == 1 then
        return cards[1]
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
-- everything goes into one master bag at a fixed spot, ready to save as a single object for another mod
local function spawnMaster(masterBag)
    spawnObjectData({
        data = masterBag,
        position = SPAWN_POSITION,
        rotation = { x = 0, y = 0, z = 0 },
    })
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

    spawnMaster(makeBag("40K Stratagems - 11e " .. version, MASTER_COLOUR, bagList))
    setStatus(version .. ": 1 bag holding " .. #bagList .. " bags / " .. deckTotal .. " decks / " .. cardTotal .. " cards")
end

-- download a URL and decode it as JSON; onDone(data) on success, onFail(message) otherwise
local function fetchJson(url, label, onDone, onFail)
    WebRequest.get(url, function(request)
        if request.is_error then
            onFail(label .. " download failed: " .. tostring(request.error))
            return
        end

        local ok, data = pcall(JSON.decode, request.text)
        if not ok or type(data) ~= "table" then
            onFail(label .. " is not valid JSON")
            return
        end

        onDone(data)
    end)
end

-- ---------------------------------------------------------------------------
-- version list (versions.json: { "latest": "v0.1", "versions": ["v0.1", ...] }, newest first)
-- ---------------------------------------------------------------------------
loadVersions = function()
    if loadingVersions then return end
    loadingVersions = true
    versionsLoaded = false
    versions = {}
    UI.setXml(buildUiXml("Loading versions..."))

    fetchJson(ROOT_URL .. "versions.json", "versions.json", function(data)
        local list = {}
        for _, v in ipairs(data.versions or {}) do
            if isValidVersion(v) then table.insert(list, v) end
        end
        versions = list
        loadingVersions = false

        if #versions == 0 then
            UI.setXml(buildUiXml("versions.json lists no valid versions"))
            return
        end

        latestVersion = hasVersion(data.latest) and data.latest or versions[1]
        if not hasVersion(selectedVersion) then
            selectedVersion = latestVersion
        end
        versionsLoaded = true
        UI.setXml(buildUiXml("Ready - pick a version and click Build"))
    end, function(message)
        loadingVersions = false
        print("[Stratagems] " .. message)
        UI.setXml(buildUiXml(message))
    end)
end

-- ---------------------------------------------------------------------------
-- build
-- ---------------------------------------------------------------------------
local function startBuild(v)
    building = true
    guidCounter = 0
    deckCounter = 0
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
    end, function(message)
        building = false
        setStatus(message)
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

    -- list failed to load (or is still loading): the button doubles as a retry
    if not versionsLoaded then
        loadVersions()
        return
    end

    startBuild(selectedVersion)
end

-- Dropdown callback. TTS passes the selected option's text (e.g. "v0.1 (latest)");
-- if it ever passes a 0-based index instead, map that back to the list.
function onVersionChosen(player, value, id)
    local v = string.match(tostring(value), "^(%S+)")
    local index = tonumber(value)
    if index and versions[index + 1] then
        v = versions[index + 1]
    end
    if hasVersion(v) then
        selectedVersion = v
        setStatus("Selected " .. v .. " - click Build")
    end
end

-- fallback if the button ever misbehaves: type  !stratagems  in chat (builds the selected version)
function onChat(message, player)
    if message == "!stratagems" then
        onBuildStratagems(player)
        return false
    end
end

function onLoad()
    if string.find(ROOT_URL, "YOUR_USER", 1, true) then
        UI.setXml(buildUiXml("Edit ROOT_URL at top of Global script first"))
        return
    end
    loadVersions()
end
