"use strict";

(() => {
  const map = window.__pairEditorMap;
  const sourceFeatures =
    window.__pairEditorStyleSpec?.sources?.network?.data?.features ?? [];
  let networkFeatures = sourceFeatures;
  const roads = new Map();
  for (const feature of sourceFeatures) {
    const props = feature.properties ?? {};
    if (props._type === "corridor_fill" && props.edge_ref) {
      roads.set(String(props.edge_ref), feature);
    }
  }

  const elements = Object.fromEntries(
    [
      "editor-status",
      "road-search",
      "road-results",
      "selection-count",
      "selected-roads",
      "relationship-form",
      "relation",
      "upper-wrap",
      "upper-road",
      "lower-road",
      "endpoint-wrap",
      "endpoint-a",
      "endpoint-b",
      "endpoint-hint",
      "replacement-wrap",
      "replacement-mode",
      "save-pair",
      "override-count",
      "override-list",
      "saved-overrides",
      "clear-selection",
      "toggle-panel",
      "editor-main",
      "download-overrides",
    ].map((id) => [id, document.getElementById(id)]),
  );

  let original = [];
  let overrides = [];
  let selected = [];
  let headMarkers = [];
  let selectionSource = "manual";
  let selectedOverrideId = "";

  function setStatus(message, kind = "") {
    elements["editor-status"].textContent = message;
    elements["editor-status"].className = `status ${kind}`;
  }

  function roadName(ref) {
    const props = roads.get(ref)?.properties ?? {};
    return props.name || props.highway || "Unnamed road";
  }

  function addOption(select, value, label) {
    const option = document.createElement("option");
    option.value = value;
    option.textContent = label;
    select.append(option);
  }

  function matchingPairs(relation, edgeA, edgeB, nodeRef = "") {
    return original.filter((row) => {
      if (row.relation !== relation) return false;
      if (relation === "connect") {
        return (
          new Set([row.edge_a, row.edge_b]).size === 2 &&
          new Set([row.edge_a, row.edge_b]).has(edgeA) &&
          new Set([row.edge_a, row.edge_b]).has(edgeB) &&
          row.node_ref === nodeRef
        );
      }
      return (
        new Set([row.upper_edge_ref, row.lower_edge_ref]).has(edgeA) &&
        new Set([row.upper_edge_ref, row.lower_edge_ref]).has(edgeB)
      );
    });
  }

  function edgeParts(ref) {
    // Casing features carry the left/right casing offsets the drawn road uses.
    const parts = networkFeatures.filter((item) =>
      String(item.properties?.edge_ref ?? "") === ref &&
      ["casing_main", "casing_head"].includes(item.properties?._type),
    );
    return parts.length ? parts : [roads.get(ref)].filter(Boolean);
  }

  function updateHighlights() {
    const source = map.getSource("pair-editor-selection");
    if (!source) return;
    const rowColors = ["#ef4444", "#10b981"];
    const features = selected.flatMap((ref, index) => {
      const color = selectionSource === "manual" ? "#c084fc" : rowColors[index % 2];
      const parts = edgeParts(ref);
      return parts.map((item) => ({
        ...item,
        properties: { ...item.properties, _highlight: color },
      }));
    });
    source.setData({ type: "FeatureCollection", features });
  }

  function dismissRoadPopups() {
    document.querySelectorAll(".maplibregl-popup").forEach((popup) => popup.remove());
  }

  function endpointCoordinates(feature) {
    const geometry = feature?.geometry;
    if (!geometry) return null;
    const lines =
      geometry.type === "MultiLineString"
        ? geometry.coordinates
        : geometry.type === "LineString"
          ? [geometry.coordinates]
          : [];
    if (!lines.length) return null;
    return {
      start: lines[0][0],
      end: lines.at(-1).at(-1),
    };
  }

  function updateHeadMarkers() {
    for (const marker of headMarkers) marker.remove();
    headMarkers = [];
    if (selected.length !== 2 || elements.relation.value !== "connect") return;

    selected.forEach((ref, edgeIndex) => {
      const coordinates = endpointCoordinates(roads.get(ref));
      if (!coordinates) return;
      for (const side of ["start", "end"]) {
        const headButton = document.createElement("button");
        headButton.type = "button";
        const selectedHead = elements[`endpoint-${edgeIndex === 0 ? "a" : "b"}`].value;
        headButton.className = [
          "head-marker",
          `edge-${edgeIndex + 1}`,
          `head-${side}`,
          selectedHead === side ? "is-selected" : "",
        ].filter(Boolean).join(" ");
        headButton.textContent = `${edgeIndex + 1}${side === "start" ? "S" : "E"}`;
        headButton.title = `Edge ${edgeIndex + 1} ${roadName(ref)} · ${ref} · ${side} head`;
        headButton.setAttribute("aria-label", headButton.title);
        headButton.addEventListener("click", (event) => {
          event.stopPropagation();
          dismissRoadPopups();
          elements[`endpoint-${edgeIndex === 0 ? "a" : "b"}`].value = side;
          updateRelationshipForm();
        });
        headMarkers.push(
          new maplibregl.Marker({ element: headButton, anchor: "center" })
            .setLngLat(coordinates[side])
            .addTo(map),
        );
      }
    });
  }

  function fitSelectedRoads() {
    const coordinates = selected.flatMap((ref) => {
      const geometry = roads.get(ref)?.geometry;
      if (!geometry) return [];
      return geometry.type === "MultiLineString"
        ? geometry.coordinates.flat(1)
        : geometry.type === "LineString"
          ? geometry.coordinates
          : [];
    });
    if (!coordinates.length) return;
    const bounds = coordinates.reduce(
      (result, point) => result.extend(point),
      new maplibregl.LngLatBounds(coordinates[0], coordinates[0]),
    );
    const panelWidth =
      document.getElementById("pair-editor")?.getBoundingClientRect().width ?? 0;
    const right = window.innerWidth > 650 ? panelWidth + 52 : 32;
    map.fitBounds(bounds, {
      padding: { top: 72, right, bottom: 72, left: 48 },
      maxZoom: 17,
      duration: 650,
    });
  }

  function effectiveOverride(row) {
    const base = original.find((item) => item.pair_id === row.pair_id) ?? {};
    const resolved = { ...base };
    for (const [field, value] of Object.entries(row)) {
      if (value !== "") resolved[field] = value;
    }
    return resolved;
  }

  function overrideRoadRefs(row) {
    const resolved = effectiveOverride(row);
    const refs = resolved.relation === "connect"
      ? [resolved.edge_a, resolved.edge_b]
      : [resolved.upper_edge_ref, resolved.lower_edge_ref];
    return [...new Set(refs.filter((ref) => roads.has(ref)))];
  }

  function selectOverride(row) {
    const resolved = effectiveOverride(row);
    selected = overrideRoadRefs(row);
    selectionSource = "override";
    selectedOverrideId = row.pair_id;
    dismissRoadPopups();
    if (["near", "cross", "connect", "order"].includes(resolved.relation)) {
      elements.relation.value = resolved.relation;
    }
    if (resolved.relation === "connect") {
      elements["endpoint-a"].value = resolved.endpoint_a || "start";
      elements["endpoint-b"].value = resolved.endpoint_b || "start";
    }
    renderEditor();
    renderOverrides();
    fitSelectedRoads();
    const missing = selected.length < 2;
    setStatus(
      missing
        ? `Override ${row.pair_id} refers to a road that is not in this map.`
        : `Showing override ${row.pair_id} on the map.`,
      missing ? "warning" : "success",
    );
  }

  function fitRoadsInVisibleMap() {
    const points = [];
    for (const feature of roads.values()) {
      const geometry = feature.geometry;
      const lines =
        geometry.type === "MultiLineString"
          ? geometry.coordinates
          : geometry.type === "LineString"
            ? [geometry.coordinates]
            : [];
      for (const line of lines) points.push(...line);
    }
    if (!points.length) return;
    const bounds = points.reduce(
      (result, point) => result.extend(point),
      new maplibregl.LngLatBounds(points[0], points[0]),
    );
    const panelWidth =
      document.getElementById("pair-editor")?.getBoundingClientRect().width ?? 0;
    const right = window.innerWidth > 650 ? Math.ceil(panelWidth + 20) : 24;
    map.fitBounds(bounds, {
      padding: { top: 28, right, bottom: 28, left: 28 },
      duration: 0,
    });
  }

  function selectRoad(ref, { zoom = false } = {}) {
    if (!roads.has(ref)) return;
    dismissRoadPopups();
    selectionSource = "manual";
    selectedOverrideId = "";
    if (selected.includes(ref)) {
      selected = selected.filter((item) => item !== ref);
      renderEditor();
      setStatus("Road removed from the selection.");
      return;
    }
    selected = selected.length < 2 ? [...selected, ref] : [ref];
    if (zoom) {
      const geometry = roads.get(ref).geometry;
      const coords =
        geometry.type === "MultiLineString"
          ? geometry.coordinates.flat()
          : geometry.coordinates;
      const bounds = coords.reduce(
        (result, point) => result.extend(point),
        new maplibregl.LngLatBounds(coords[0], coords[0]),
      );
      map.fitBounds(bounds, { padding: 90, maxZoom: 17, duration: 500 });
    }
    renderEditor();
  }

  function makeRoadButton(ref) {
    const feature = roads.get(ref);
    const props = feature?.properties ?? {};
    const button = document.createElement("button");
    button.type = "button";
    button.className = "road-result";
    const title = document.createElement("strong");
    title.textContent = props.name || "Unnamed road";
    const detail = document.createElement("span");
    detail.textContent = `${props.highway || "road"} · ${ref}`;
    button.append(title, detail);
    button.addEventListener("click", () => selectRoad(ref, { zoom: true }));
    return button;
  }

  function renderSearchResults() {
    const needle = elements["road-search"].value.trim().toLocaleLowerCase();
    elements["road-results"].replaceChildren();
    if (!needle) return;
    let count = 0;
    for (const [ref, feature] of roads) {
      const props = feature.properties ?? {};
      const text =
        `${ref} ${props.name ?? ""} ${props.highway ?? ""}`.toLocaleLowerCase();
      if (!text.includes(needle)) continue;
      elements["road-results"].append(makeRoadButton(ref));
      count += 1;
      if (count === 25) break;
    }
    if (!count) {
      const empty = document.createElement("p");
      empty.className = "empty-note";
      empty.textContent = "No matching roads.";
      elements["road-results"].append(empty);
    }
  }

  function roadDetails(ref) {
    const props = roads.get(ref)?.properties ?? {};
    const flags = [props.bridge ? "bridge" : "", props.tunnel ? "tunnel" : ""].filter(Boolean);
    const rows = [
      ["Highway", props.highway],
      ["Level", props.level],
      ["Fill level", props.fill_level],
      ["Casing start / level / end",
        [props.casing_start, props.casing_level, props.casing_end].join(" / ")],
      ["Band", props.band],
      ["Bridge / tunnel", flags.length ? flags.join(", ") : "no"],
      ["Lanes", props.lanes],
      ["Width", props.width_m == null ? null : `${props.width_m} m`],
      ["Casing", props.casing_m == null ? null : `${props.casing_m} m`],
      ["Oneway", props.oneway == null ? null : (props.oneway ? "yes" : "no")],
      ["Length", props.length_m == null ? null : `${Number(props.length_m).toFixed(1)} m`],
      ["Max speed", props.maxspeed_kmh == null ? null : `${props.maxspeed_kmh} km/h`],
      ["Surface", props.surface],
    ];
    const list = document.createElement("dl");
    list.className = "road-details";
    for (const [key, value] of rows) {
      if (value == null || value === "") continue;
      const term = document.createElement("dt");
      term.textContent = key;
      const desc = document.createElement("dd");
      desc.textContent = String(value);
      list.append(term, desc);
    }
    return list;
  }

  function renderSelection() {
    elements["selected-roads"].replaceChildren();
    elements["selection-count"].textContent = `${selected.length} / 2`;
    selected.forEach((ref, index) => {
      const card = document.createElement("div");
      card.className = "selected-road";
      if (selectionSource === "override") card.classList.add("from-override");
      const label = document.createElement("span");
      label.className = "selected-road-index";
      label.textContent = `0${index + 1}`;
      const text = document.createElement("div");
      const name = document.createElement("strong");
      name.textContent = roadName(ref);
      const id = document.createElement("small");
      id.textContent = ref;
      text.append(name, id);
      card.append(label, text, roadDetails(ref));
      elements["selected-roads"].append(card);
    });
    elements["relationship-form"].hidden =
      selected.length !== 2 || selectionSource !== "manual";
    if (selected.length === 2 && selectionSource === "manual") updateRelationshipForm();
    elements["save-pair"].disabled =
      selected.length !== 2 || selectionSource !== "manual";
    updateHighlights();
    updateHeadMarkers();
  }

  function updateRelationshipForm() {
    const [edgeA, edgeB] = selected;
    const relation = elements.relation.value;
    const previousHeadA = elements["endpoint-a"].value || "start";
    const previousHeadB = elements["endpoint-b"].value || "start";
    const isConnect = relation === "connect";
    elements["upper-wrap"].hidden = isConnect;
    elements["endpoint-wrap"].hidden = !isConnect;
    elements["replacement-wrap"].hidden = true;

    elements["upper-road"].replaceChildren();
    addOption(elements["upper-road"], edgeA, `${roadName(edgeA)} · ${edgeA}`);
    addOption(elements["upper-road"], edgeB, `${roadName(edgeB)} · ${edgeB}`);
    renderLowerRoad();

    for (const [key, ref] of [["endpoint-a", edgeA], ["endpoint-b", edgeB]]) {
      const select = elements[key];
      select.replaceChildren();
      addOption(select, "start", `${roadName(ref)} · start head`);
      addOption(select, "end", `${roadName(ref)} · end head`);
    }
    elements["endpoint-a"].value = previousHeadA;
    elements["endpoint-b"].value = previousHeadB;
    elements["endpoint-hint"].textContent =
      "Map markers: 1S/1E belong to road A; 2S/2E belong to road B. Click a marker to choose that head.";

    updateReplacementOptions();
    updateHeadMarkers();
  }

  function renderLowerRoad() {
    const upper = elements["upper-road"].value || selected[0];
    const lower = selected.find((ref) => ref !== upper);
    elements["lower-road"].textContent = lower
      ? `Other road: ${roadName(lower)} · ${lower}`
      : "";
    elements["save-pair"].disabled = selected.length !== 2;
  }

  function updateReplacementOptions() {
    const [edgeA, edgeB] = selected;
    const relation = elements.relation.value;
    const matches = matchingPairs(
      relation,
      edgeA,
      edgeB,
      "",
    );
    if (!matches.length) {
      elements["replacement-wrap"].hidden = true;
      return;
    }
    elements["replacement-wrap"].hidden = false;
    elements["replacement-mode"].replaceChildren();
    addOption(elements["replacement-mode"], "", "Add a new relationship");
    for (const row of matches) {
      addOption(
        elements["replacement-mode"],
        row.pair_id,
        `Replace ${row.pair_id} · ${row.upper_edge_ref || row.node_ref}`,
      );
    }
  }

  function renderEditor() {
    renderSelection();
    renderSearchResults();
  }

  function buildOverride() {
    const [edgeA, edgeB] = selected;
    const relation = elements.relation.value;
    const existingId = elements["replacement-mode"].value;
    if (existingId) {
      const existing = original.find((row) => row.pair_id === existingId);
      const row = {
        action: "replace",
        pair_id: existingId,
        relation,
      };
      if (relation === "connect") {
        if (existing.endpoint_a !== elements["endpoint-a"].value) {
          row.endpoint_a = elements["endpoint-a"].value;
        }
        if (existing.endpoint_b !== elements["endpoint-b"].value) {
          row.endpoint_b = elements["endpoint-b"].value;
        }
      } else {
        const upper = elements["upper-road"].value;
        const lower = selected.find((ref) => ref !== upper);
        if (existing.upper_edge_ref !== upper) row.upper_edge_ref = upper;
        if (existing.lower_edge_ref !== lower) row.lower_edge_ref = lower;
      }
      return row;
    }

    const row = {
      action: "add",
      pair_id: crypto.randomUUID().replaceAll("-", "").slice(0, 20),
      relation,
      edge_a: edgeA,
      edge_b: edgeB,
      enabled: "true",
    };
    if (relation === "connect") {
      row.node_ref = "";
      row.endpoint_a = elements["endpoint-a"].value;
      row.endpoint_b = elements["endpoint-b"].value;
    } else {
      row.upper_edge_ref = elements["upper-road"].value;
      row.lower_edge_ref = selected.find((ref) => ref !== row.upper_edge_ref);
    }
    return row;
  }

  let levelSummary = "";

  function applyNetwork(network) {
    if (!network) return;
    const source = map.getSource("network");
    if (!source) return;
    networkFeatures = network.features;
    for (const feature of network.features) {
      const props = feature.properties ?? {};
      if (props._type === "corridor_fill" && props.edge_ref) {
        roads.set(String(props.edge_ref), feature);
      }
    }
    source.setData({ type: "FeatureCollection", features: network.features });
    updateHighlights();
    const { roads: roadCount, pairs, levels } = network.summary;
    levelSummary = `${roadCount.toLocaleString()} roads · ${pairs.toLocaleString()} active relationships · solved levels ${levels.join(", ")}`;
  }

  async function savePair() {
    elements["save-pair"].disabled = true;
    setStatus("Saving override…");
    try {
      const response = await fetch("/api/overrides", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ row: buildOverride() }),
      });
      const payload = await response.json();
      if (!response.ok) throw new Error(payload.error || "The override could not be saved.");
      overrides = payload.overrides;
      applyNetwork(payload.network);
      selected = [];
      selectionSource = "manual";
      selectedOverrideId = "";
      renderEditor();
      renderOverrides();
      setStatus(`Override saved. ${levelSummary}`, "success");
    } catch (error) {
      setStatus(error.message, "error");
      elements["save-pair"].disabled = selected.length !== 2;
    }
  }

  function renderOverrides() {
    elements["override-count"].textContent = `(${overrides.length})`;
    elements["override-list"].replaceChildren();
    for (const row of overrides) {
      const card = document.createElement("div");
      card.className = "override-row";
      if (row.pair_id === selectedOverrideId) card.classList.add("is-selected");
      const select = document.createElement("button");
      select.type = "button";
      select.className = "override-select";
      select.setAttribute("aria-pressed", String(row.pair_id === selectedOverrideId));
      select.addEventListener("click", () => {
        if (row.pair_id === selectedOverrideId) {
          selected = [];
          selectedOverrideId = "";
          selectionSource = "manual";
          renderEditor();
          renderOverrides();
          setStatus("Override unselected.");
        } else {
          selectOverride(row);
        }
      });
      const resolved = effectiveOverride(row);
      const action = document.createElement("span");
      action.className = `override-action action-${row.action}`;
      action.textContent = row.action.toUpperCase();
      const description = document.createElement("strong");
      description.textContent =
        `${resolved.relation || "relationship"} · ${resolved.edge_a || resolved.upper_edge_ref || "?"} ↔ ${resolved.edge_b || resolved.lower_edge_ref || "?"}`;
      const pairId = document.createElement("small");
      pairId.textContent = row.pair_id;
      select.append(action, description, pairId);
      const remove = document.createElement("button");
      remove.type = "button";
      remove.className = "override-delete";
      remove.textContent = "Delete";
      remove.setAttribute("aria-label", `Delete override ${row.pair_id}`);
      remove.addEventListener("click", () => deleteOverride(row.pair_id));
      card.append(select, remove);
      elements["override-list"].append(card);
    }
    if (!overrides.length) {
      const empty = document.createElement("p");
      empty.className = "empty-note";
      empty.textContent = "No saved overrides yet.";
      elements["override-list"].append(empty);
    }
  }

  async function deleteOverride(pairId) {
    const row = overrides.find((item) => item.pair_id === pairId);
    if (!row || !window.confirm(`Delete ${row.action} override ${pairId}?`)) return;
    setStatus(`Deleting override ${pairId}…`);
    try {
      const response = await fetch("/api/overrides/delete", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ pair_id: pairId }),
      });
      const payload = await response.json();
      if (!response.ok) throw new Error(payload.error || "The override could not be deleted.");
      overrides = payload.overrides;
      applyNetwork(payload.network);
      if (selectedOverrideId === pairId) {
        selected = [];
        selectedOverrideId = "";
        selectionSource = "manual";
        renderEditor();
      }
      renderOverrides();
      setStatus(`Override deleted. ${levelSummary}`, "success");
    } catch (error) {
      setStatus(error.message, "error");
    }
  }

  function csvCell(value) {
    const text = String(value ?? "");
    return `"${text.replaceAll('"', '""')}"`;
  }

  function downloadCsv() {
    const columns = [
      "action",
      "pair_id",
      "relation",
      "edge_a",
      "edge_b",
      "node_ref",
      "endpoint_a",
      "endpoint_b",
      "upper_edge_ref",
      "lower_edge_ref",
      "enabled",
    ];
    const content = [
      columns.join(","),
      ...overrides.map((row) => columns.map((field) => csvCell(row[field])).join(",")),
    ].join("\r\n");
    const url = URL.createObjectURL(new Blob([content], { type: "text/csv" }));
    const link = document.createElement("a");
    link.href = url;
    link.download = "road_pairs_overrides.csv";
    link.click();
    URL.revokeObjectURL(url);
  }

  async function load() {
    const response = await fetch("/api/data");
    if (!response.ok) throw new Error("Could not load pair tables from the local server.");
    const data = await response.json();
    original = data.original;
    overrides = data.overrides;
    renderOverrides();
    setStatus("Solving road levels…");
    const levelResponse = await fetch("/api/network");
    if (levelResponse.ok) {
      const network = await levelResponse.json();
      if (!map.getSource("network")) await new Promise((resolve) => map.once("load", resolve));
      applyNetwork(network);
    }
    setStatus(
      levelSummary ||
        `${roads.size.toLocaleString()} roads · ${data.effective_count.toLocaleString()} active relationships`,
      "success",
    );
  }

  document.addEventListener("DOMContentLoaded", () => {
    elements["road-search"].addEventListener("input", renderSearchResults);
    elements.relation.addEventListener("change", updateRelationshipForm);
    elements["upper-road"].addEventListener("change", renderLowerRoad);
    elements["upper-road"].addEventListener("change", updateReplacementOptions);
    elements["endpoint-a"].addEventListener("change", () => {
      updateReplacementOptions();
      updateHeadMarkers();
    });
    elements["endpoint-b"].addEventListener("change", () => {
      updateReplacementOptions();
      updateHeadMarkers();
    });
    elements["save-pair"].addEventListener("click", savePair);
    elements["clear-selection"].addEventListener("click", () => {
      selected = [];
      selectionSource = "manual";
      selectedOverrideId = "";
      renderEditor();
      setStatus("Selection cleared.");
    });
    elements["toggle-panel"].addEventListener("click", () => {
      const panel = document.getElementById("pair-editor");
      const collapsed = panel.classList.toggle("collapsed");
      elements["toggle-panel"].setAttribute("aria-expanded", String(!collapsed));
      elements["toggle-panel"].setAttribute(
        "aria-label",
        collapsed ? "Expand pair editor" : "Collapse pair editor",
      );
      elements["toggle-panel"].title = collapsed ? "Expand panel" : "Collapse panel";
      elements["toggle-panel"].textContent = collapsed ? "‹" : "›";
      window.setTimeout(() => map.resize(), 240);
    });
    elements["download-overrides"].addEventListener("click", downloadCsv);

    map.on("load", () => {
      map.addSource("pair-editor-selection", {
        type: "geojson",
        data: { type: "FeatureCollection", features: [] },
      });
      const corridorFillLayer = map.getStyle().layers.find((layer) =>
        layer.type === "line" &&
        layer.source === "network" &&
        JSON.stringify(layer.paint?.["line-color"] ?? "").includes("fill_color") &&
        JSON.stringify(layer.filter ?? "").includes("corridor_fill"),
      );
      const casingLayer = map.getStyle().layers.find((layer) =>
        layer.type === "line" &&
        layer.source === "network" &&
        JSON.stringify(layer.filter ?? "").includes("casing_main") &&
        layer.paint?.["line-width"],
      );
      // The casing is wider than the fill, so size the highlight from the casing layer.
      const baseWidth = (casingLayer ?? corridorFillLayer)?.paint?.["line-width"];
      if (!baseWidth) {
        setStatus("Could not find the road width style for selection highlighting.", "error");
        return;
      }
      // MapLibre only allows "zoom" at the top level, so add to each interpolate stop.
      const widthPlus = (extra) =>
        Array.isArray(baseWidth) && baseWidth[0] === "interpolate"
          ? baseWidth.map((item, index) =>
              index >= 3 && index % 2 === 0 ? ["+", item, extra] : item)
          : baseWidth;
      const highlightWidth = widthPlus(3);
      map.addLayer({
        id: "pair-editor-selection-highlight",
        type: "line",
        source: "pair-editor-selection",
        layout: { "line-cap": "round", "line-join": "round" },
        paint: {
          "line-color": ["coalesce", ["get", "_highlight"], "#c084fc"],
          "line-width": highlightWidth,
          "line-offset": casingLayer?.paint?.["line-offset"] ?? 0,
          "line-opacity": 1,
        },
      });
      // Replace the page's hover highlight, which copies a tile-clipped fragment of the
      // edge and sits underneath the selection layer, with one drawn from the full edge.
      const builtInHover = map.getSource("hover_source");
      if (builtInHover) {
        builtInHover.setData({ type: "FeatureCollection", features: [] });
        builtInHover.setData = () => builtInHover;
      }
      map.addSource("pair-editor-hover", {
        type: "geojson",
        data: { type: "FeatureCollection", features: [] },
      });
      for (const [id, color, extra] of [
        ["pair-editor-hover-glow", "#00f0ff", 6],
        ["pair-editor-hover-core", "#ffffff", 0],
      ]) {
        map.addLayer({
          id,
          type: "line",
          source: "pair-editor-hover",
          layout: { "line-cap": "round", "line-join": "round" },
          paint: {
            "line-color": color,
            "line-opacity": extra ? 0.85 : 0.55,
            "line-offset": casingLayer?.paint?.["line-offset"] ?? 0,
            "line-width": widthPlus(extra),
          },
        });
      }
      let hoveredRef = "";
      const setHover = (ref) => {
        if (ref === hoveredRef) return;
        hoveredRef = ref;
        map.getSource("pair-editor-hover").setData({
          type: "FeatureCollection",
          features: ref ? edgeParts(ref) : [],
        });
      };
      const pixelDistance = (ref, point) => {
        const geometry = roads.get(ref)?.geometry;
        if (!geometry) return Infinity;
        const lines = geometry.type === "MultiLineString" ? geometry.coordinates : [geometry.coordinates];
        let best = Infinity;
        for (const line of lines) {
          let previous = map.project(line[0]);
          for (let i = 1; i < line.length; i += 1) {
            const current = map.project(line[i]);
            const dx = current.x - previous.x;
            const dy = current.y - previous.y;
            const lengthSquared = dx * dx + dy * dy;
            const t = lengthSquared
              ? Math.max(0, Math.min(1, ((point.x - previous.x) * dx + (point.y - previous.y) * dy) / lengthSquared))
              : 0;
            best = Math.min(best, Math.hypot(point.x - (previous.x + t * dx), point.y - (previous.y + t * dy)));
            previous = current;
          }
        }
        return best;
      };
      // How far from the centreline the pointer still counts as on the drawn road.
      const roadSlack = (ref, point) => {
        const props = roads.get(ref)?.properties ?? {};
        const metres = Number(props.width_m ?? 0) / 2 + Number(props.casing_m ?? 0);
        const lat = map.unproject(point).lat;
        const metresPerPixel =
          (40075016.686 * Math.cos((lat * Math.PI) / 180)) / (512 * 2 ** map.getZoom());
        return metres / metresPerPixel + 4;
      };
      // Candidates come from what is drawn under the cursor; the winner is the edge whose
      // full centreline is closest, so overlapping or neighbouring edges resolve predictably.
      const pickRoad = (point) => {
        const box = [[point.x - 6, point.y - 6], [point.x + 6, point.y + 6]];
        const refs = new Set(map.queryRenderedFeatures(box)
          .filter((item) =>
            item.source === "network" &&
            ["corridor_fill", "casing_main", "casing_head"].includes(item.properties?._type) &&
            roads.has(String(item.properties?.edge_ref ?? "")))
          .map((item) => String(item.properties.edge_ref)));
        let bestRef = "";
        let bestScore = Infinity;
        for (const ref of refs) {
          const score = Math.round(pixelDistance(ref, point) - roadSlack(ref, point)) -
            (selected.includes(ref) ? 0.5 : 0) -
            Number(roads.get(ref).properties.level ?? 0) * 0.01;
          if (score < bestScore) {
            bestScore = score;
            bestRef = ref;
          }
        }
        return bestScore <= 0 ? bestRef : "";
      };
      // Hover is resolved only once the pointer rests (dwell), not while it is moving, and is
      // re-checked periodically so it follows map changes under a stationary pointer.
      const HOVER_DWELL_MS = 120;
      const HOVER_REFRESH_MS = 300;
      let lastPoint = null;
      let dwellTimer = 0;
      let refreshTimer = 0;
      const stillOnHovered = (point) =>
        Boolean(hoveredRef) &&
        pixelDistance(hoveredRef, point) <= roadSlack(hoveredRef, point);
      const resolveHover = () => {
        if (!lastPoint || map.isMoving()) return;
        if (stillOnHovered(lastPoint)) return;
        const ref = pickRoad(lastPoint);
        map.getCanvas().style.cursor = ref ? "pointer" : "";
        setHover(ref);
      };
      const stopHover = () => {
        clearTimeout(dwellTimer);
        clearInterval(refreshTimer);
        refreshTimer = 0;
        setHover("");
        map.getCanvas().style.cursor = "";
      };
      map.on("mousemove", (event) => {
        lastPoint = event.point;
        clearTimeout(dwellTimer);
        // Sliding along the highlighted edge keeps it; only leaving it starts a new dwell.
        if (stillOnHovered(event.point)) return;
        setHover("");
        map.getCanvas().style.cursor = "";
        dwellTimer = setTimeout(resolveHover, HOVER_DWELL_MS);
        if (!refreshTimer) refreshTimer = setInterval(resolveHover, HOVER_REFRESH_MS);
      });
      map.on("movestart", stopHover);
      map.on("moveend", () => {
        if (!lastPoint) return;
        clearTimeout(dwellTimer);
        dwellTimer = setTimeout(resolveHover, HOVER_DWELL_MS);
        if (!refreshTimer) refreshTimer = setInterval(resolveHover, HOVER_REFRESH_MS);
      });
      map.getContainer().addEventListener("mouseleave", () => {
        lastPoint = null;
        stopHover();
      });
      fitRoadsInVisibleMap();
      map.on("click", (event) => {
        const ref = pickRoad(event.point);
        if (ref) selectRoad(ref);
      });
    });

    load().catch((error) => setStatus(error.message, "error"));
  });
})();
