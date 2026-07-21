/*!
 * roadstyle.js — the ONE canonical browser renderer for the roadstyle `spec/1` format.
 *
 * Single source of truth: the Python library (`roadstyle.emit.to_html`) inlines THIS exact file,
 * and you can also drop it into any page on its own:
 *
 *     <script src="https://cdn.jsdelivr.net/npm/leaflet@1.9.4/dist/leaflet.js"></script>
 *     <script src="roadstyle.js"></script>
 *     <script>
 *       const m = new RoadStyleMap("map");
 *       m.load("map_data.json", "interaction_config.json");   // spec + optional interaction config
 *     </script>
 *
 * It reads only the stable `__rs_*` per-feature properties baked by Python, so the same renderer
 * works whether roads are styled by class, by category, or by a numeric ramp.
 *
 * No build step, no dependencies except Leaflet (loaded by the host page).
 */
(function (global, factory) {
  // UMD-ish: attach to window for <script>, support CommonJS for tooling. No ESM `export` keyword
  // (that would break classic <script> use); ESM users can `import "./roadstyle.js"` for the global.
  var api = factory();
  if (typeof module === "object" && module.exports) module.exports = api;
  global.RoadStyleMap = api.RoadStyleMap;
  global.RoadStyle = api;
})(typeof window !== "undefined" ? window : this, function () {
  "use strict";

  var VERSION = "1.0";

  var DEFAULT_OPTIONS = {
    // Hover (mouse over a road)
    hoverColor: "#FFFFFF",
    hoverExtraWidth: 2,
    hoverOpacity: 1.0,
    // Click selection — 3-layer neon-violet glow (glow under, casing, white core on top).
    // The widths below are minimums; the highlight always grows to sit over the edge it covers.
    selectionStyle: {
      glow: { color: "#FF00FF", width: 12, opacity: 0.4 },
      casing: { color: "#000000", width: 7, opacity: 1.0 },
      core: { color: "#FFFFFF", width: 4, opacity: 1.0 },
    },
    // Leaflet map toggles
    doubleClickZoom: true,
    zoomControl: true,
    // Selection-result callbacks. Set these in JS (an interaction_config.json can't carry
    // functions) via the constructor options or `.on("select"/"deselect", fn)`.
    onSelect: null, // function(feature, layer) — fired when an edge is selected
    onDeselect: null, // function(prevFeature)   — fired when the selection is cleared
    // Optional built-in UI widgets (opt-in — no front-end code required to get a usable map).
    widgets: {
      legend: true, // render the spec's legend (if present)
      filter: false, // a road-class checkbox panel
      basemap: false, // a base-layer switcher over the spec's `basemaps` (re-picks casing on change)
      colors: false, // a "colour by" picker over the spec's `color_options` (recolours client-side)
    },
  };

  function isUrl(x) {
    return typeof x === "string";
  }

  function deepMergeOptions(base, over) {
    if (!over) return base;
    var out = Object.assign({}, base, over);
    out.selectionStyle = Object.assign({}, base.selectionStyle, over.selectionStyle || {});
    if (over.selectionStyle) {
      ["glow", "casing", "core"].forEach(function (k) {
        out.selectionStyle[k] = Object.assign({}, base.selectionStyle[k], over.selectionStyle[k] || {});
      });
    }
    out.widgets = Object.assign({}, base.widgets, over.widgets || {});
    return out;
  }

  function RoadStyleMap(containerId, options) {
    this.containerId = containerId;
    this.options = deepMergeOptions(DEFAULT_OPTIONS, options || {});
    this.map = L.map(containerId, {
      doubleClickZoom: this.options.doubleClickZoom,
      zoomControl: this.options.zoomControl,
    });
    this.spec = null;
    this.casingLayer = null;
    this.fillLayer = null;
    this.highlightLayer = null;
    this.selectedLayer = null; // the fill sub-layer currently selected (null = none)
    this.selected = null; // the selected GeoJSON feature (null = none)
    this.activeFilters = null; // null = show all
    this._handlers = {}; // event bus: { eventName: [fn, …] } (see on/off/emit)
    this._panelStacks = {}; // corner -> stack container for addPanel() panels
    this._colorProp = "__rs_fill"; // the per-edge fill prop the fill style reads (see setColorField)
    this._colorActiveIndex = 0; // index into spec.color_options of the active "colour by" option
    this._activeLegend = null; // the legend currently shown (swaps with the colour option)
  }

  RoadStyleMap.version = VERSION;

  // Load a spec (URL or object) and, optionally, an interaction config (URL or object).
  RoadStyleMap.prototype.load = function (specOrUrl, configOrUrl) {
    var self = this;
    var specP = isUrl(specOrUrl)
      ? fetch(specOrUrl).then(function (r) { return r.json(); })
      : Promise.resolve(specOrUrl);
    return specP.then(function (spec) {
      self.spec = spec;
      self._initColorState();
      var cfgP = configOrUrl ? self.loadInteractionConfig(configOrUrl) : Promise.resolve();
      return cfgP.then(function () {
        self._renderBaseMap();
        self._renderRoads();
        self._renderWidgets();
        self.emit("ready", self, spec);
        return self;
      });
    });
  };

  RoadStyleMap.prototype.loadInteractionConfig = function (configOrUrl) {
    var self = this;
    var p = isUrl(configOrUrl)
      ? fetch(configOrUrl).then(function (r) { return r.json(); })
      : Promise.resolve(configOrUrl);
    return p.then(function (cfg) {
      self.options = deepMergeOptions(self.options, cfg);
    });
  };

  // Unique __rs_class values present in the data — use to build your own UI.
  RoadStyleMap.prototype.getRoadClasses = function () {
    if (!this.spec) return [];
    var seen = {};
    (this.spec.geojson.features || []).forEach(function (f) {
      var c = f.properties && f.properties.__rs_class;
      if (c != null) seen[c] = true;
    });
    return Object.keys(seen);
  };

  // Restrict visible road classes (null/undefined => show all).
  RoadStyleMap.prototype.setFilter = function (allowedClasses) {
    this.activeFilters = allowedClasses && allowedClasses.length ? allowedClasses : null;
    if (this.casingLayer) this.casingLayer.setStyle(this._casingStyle.bind(this));
    if (this.fillLayer) this.fillLayer.setStyle(this._fillStyle.bind(this));
    // A hidden road shouldn't keep its selection highlight.
    if (this.selectedLayer && this.selectedLayer.feature &&
        !this._visible(this.selectedLayer.feature.properties)) {
      this.clearSelection();
    }
  };

  RoadStyleMap.prototype._visible = function (p) {
    return !this.activeFilters || this.activeFilters.indexOf(p.__rs_class) !== -1;
  };

  RoadStyleMap.prototype._casingStyle = function (f) {
    var p = f.properties;
    // Casing is theme-driven (the baked __rs_casing), consistent with the web/folium backends — it
    // does not re-pick by base-map darkness, so the theme's casing holds on every base. A null
    // __rs_casing means "no casing" (minor roads).
    var casing = p.__rs_casing;
    if (!casing || !p.__rs_cw) return { opacity: 0, weight: 0 };
    return {
      color: casing,
      weight: p.__rs_cw,
      opacity: this._visible(p) ? p.__rs_cop : 0,
      lineCap: "butt",
      lineJoin: "round",
    };
  };

  RoadStyleMap.prototype._fillStyle = function (f) {
    var p = f.properties;
    // The active "colour by" option swaps which baked fill prop is read (default __rs_fill); fall
    // back to __rs_fill if a variant prop is missing on some feature.
    var fill = p[this._colorProp];
    return {
      color: fill != null ? fill : p.__rs_fill,
      weight: p.__rs_w,
      opacity: this._visible(p) ? p.__rs_op : 0,
      dashArray: p.__rs_dash,
      lineCap: "butt",
      lineJoin: "round",
    };
  };

  RoadStyleMap.prototype._tileLayer = function (bm) {
    return L.tileLayer(bm.url, {
      attribution: bm.attr || "",
      subdomains: bm.subdomains || "abc",
      maxZoom: 20,
    });
  };

  RoadStyleMap.prototype._renderBaseMap = function () {
    var self = this;
    var active = (this.spec && this.spec.basemap) || {};
    // The full selectable set (for the switcher); fall back to just the active base map.
    var list =
      this.spec && this.spec.basemaps && this.spec.basemaps.length
        ? this.spec.basemaps
        : active.url
        ? [active]
        : [];
    this.baseLayers = {}; // label -> Leaflet layer  (consumed by the basemap switcher widget)
    this.baseMeta = {}; // label -> basemap meta (darkness / satellite flags)
    list.forEach(function (bm) {
      if (!bm.url) return;
      self.baseLayers[bm.label] = self._tileLayer(bm);
      self.baseMeta[bm.label] = bm;
    });
    this.isDark = !!active.is_dark; // drives which baked casing (__rs_casing_light/_dark) is used
    var current = this.baseLayers[active.label] || this.baseLayers[Object.keys(this.baseLayers)[0]];
    if (current) {
      current.addTo(this.map);
      this._applyBaseMapFx(this.baseMeta[active.label] || active);
    }
    if (this.spec && this.spec.bounds) this.map.fitBounds(this.spec.bounds);
  };

  // Visual tweaks tied to the active base map (e.g. dim/saturate satellite imagery).
  RoadStyleMap.prototype._applyBaseMapFx = function (bm) {
    var c = this.map.getContainer();
    if (c && c.classList) c.classList.toggle("rs-satellite", !!(bm && bm.satellite));
  };

  // Build the tooltip HTML for a feature from the spec's `tooltip` field list. Shared by the
  // hover tooltip and the pinned (click-to-pin) tooltip so the two can never drift.
  RoadStyleMap.prototype._tooltipHtml = function (props) {
    var tip = (this.spec && this.spec.tooltip) || [];
    return tip
      .map(function (k) {
        return "<b>" + k + "</b>: " + (props[k] == null ? "" : props[k]);
      })
      .join("<br>");
  };

  RoadStyleMap.prototype._renderRoads = function () {
    var self = this;
    var gj = this.spec.geojson;
    var tip = this.spec.tooltip || [];

    // Geometry sandwich: casing layer under, fill layer over.
    this.casingLayer = L.geoJSON(gj, { style: this._casingStyle.bind(this) }).addTo(this.map);
    this.fillLayer = L.geoJSON(gj, {
      style: this._fillStyle.bind(this),
      onEachFeature: function (ft, layer) {
        if (tip.length) {
          layer.bindTooltip(self._tooltipHtml(ft.properties), { sticky: true });
        }
        layer.on("mouseover", function (e) {
          if (!self._visible(ft.properties)) return;
          if (self.selectedLayer === layer) {
            e.target.closeTooltip(); // this edge is pinned — don't stack the hover tooltip on it
            return; // and don't fight the selection highlight
          }
          e.target.setStyle({
            color: self.options.hoverColor,
            weight: ft.properties.__rs_w + self.options.hoverExtraWidth,
            opacity: self.options.hoverOpacity,
          });
          e.target.bringToFront();
        });
        layer.on("mouseout", function (e) {
          self.fillLayer.resetStyle(e.target);
        });
        // Click toggles selection AND pins the tooltip: click an edge to select + pin it, click it
        // again (or click the map background) to deselect and unpin.
        layer.on("click", function (e) {
          if (L.DomEvent) L.DomEvent.stopPropagation(e); // don't let the map-click clear it
          if (self.selectedLayer === layer) {
            self.clearSelection();
          } else {
            self.selectFeature(layer, ft, e.latlng);
          }
        });
      },
    }).addTo(this.map);

    // Clicking the map background (not a road) clears the selection.
    this.map.on("click", function () { self.clearSelection(); });
  };

  // Select an edge: draw the highlight, pin its tooltip open, remember it, and hand the feature
  // back to the host page. `latlng` (the click point) anchors the pinned tooltip; when absent
  // (programmatic selection) it falls back to the edge's centre.
  RoadStyleMap.prototype.selectFeature = function (layer, feature, latlng) {
    this.clearSelection(); // deselects any previous edge (fires onDeselect for it)
    this.selectedLayer = layer || null;
    this.selected = feature || null;
    this.highlightRoad(feature);
    if (layer && layer.closeTooltip) layer.closeTooltip(); // drop the hover tooltip; pin instead
    this._pinTooltip(feature, layer, latlng);
    if (typeof this.options.onSelect === "function") this.options.onSelect(feature, layer);
    this.emit("select", feature, layer);
  };

  // Pin the tooltip open at `latlng` (or the edge centre) so it survives mouseout — the hover
  // tooltip otherwise vanishes the moment the cursor leaves. The pinned tooltip is interactive so
  // its text stays selectable (copy the road's details straight out of it). Removed by
  // clearSelection() (click the edge again or the map background to unpin).
  RoadStyleMap.prototype._pinTooltip = function (feature, layer, latlng) {
    var html = this._tooltipHtml((feature && feature.properties) || {});
    if (!html) return; // no tooltip fields configured → nothing to pin
    var at = latlng || (layer && layer.getBounds && layer.getBounds().getCenter());
    if (!at) return;
    this.pinnedTooltip = L.tooltip({
      permanent: true,
      interactive: true, // keep the text selectable so it can be copied out
      direction: "top",
      offset: [0, -4],
      className: "rs-tip-pinned",
    })
      .setLatLng(at)
      .setContent("📌 " + html)
      .addTo(this.map);

    // Keep clicks/selection inside the tooltip from reaching the map (which would unpin it).
    var el = this.pinnedTooltip.getElement();
    if (el && L.DomEvent) L.DomEvent.disableClickPropagation(el);
  };

  // Remove any active selection highlight, notifying the host page if something was selected.
  RoadStyleMap.prototype.clearSelection = function () {
    var prev = this.selected || null;
    if (this.highlightLayer) {
      this.map.removeLayer(this.highlightLayer);
      this.highlightLayer = null;
    }
    if (this.pinnedTooltip) {
      this.pinnedTooltip.remove(); // unpin the tooltip
      this.pinnedTooltip = null;
    }
    this.selectedLayer = null;
    this.selected = null;
    if (prev && typeof this.options.onDeselect === "function") this.options.onDeselect(prev);
    if (prev) this.emit("deselect", prev);
  };

  // The currently selected GeoJSON feature (its geometry + properties incl. __rs_class), or null.
  RoadStyleMap.prototype.getSelection = function () {
    return this.selected || null;
  };

  // ── Event bus ────────────────────────────────────────────────────────────────
  // Subscribe to a map event: "ready" (map, spec), "select" (feature, layer),
  // "deselect" (prevFeature), "colorchange" (option). Chainable; call several times to add
  // several listeners for the same event (unlike the legacy single onSelect/onDeselect options,
  // which still fire alongside these).
  RoadStyleMap.prototype.on = function (event, fn) {
    (this._handlers[event] || (this._handlers[event] = [])).push(fn);
    return this; // chainable
  };

  // Unsubscribe. With no `fn`, drops every listener for that event.
  RoadStyleMap.prototype.off = function (event, fn) {
    var hs = this._handlers[event];
    if (!hs) return this;
    if (!fn) delete this._handlers[event];
    else this._handlers[event] = hs.filter(function (h) { return h !== fn; });
    return this;
  };

  // Fire an event to all subscribers (one throwing listener doesn't stop the others).
  RoadStyleMap.prototype.emit = function (event) {
    var args = Array.prototype.slice.call(arguments, 1);
    (this._handlers[event] || []).forEach(function (h) {
      try { h.apply(null, args); }
      catch (e) { if (typeof console !== "undefined") console.error("[roadstyle] " + event + " handler:", e); }
    });
    return this;
  };

  // ── Client-side recolouring ("colour by" options) ─────────────────────────────
  // The "colour by" options baked into the spec (each: {name, prop, legend}); [] if none.
  RoadStyleMap.prototype.getColorOptions = function () {
    return (this.spec && this.spec.color_options) || [];
  };

  // The active option's index (into getColorOptions()).
  RoadStyleMap.prototype.getColorField = function () {
    return this._colorActiveIndex;
  };

  // Recolour the roads to a "colour by" option — by name or by index — with no re-render: the
  // option's baked fill prop is swapped in, the legend follows, and a "colorchange" event fires.
  RoadStyleMap.prototype.setColorField = function (nameOrIndex) {
    var opts = this.getColorOptions();
    if (!opts.length) return this;
    var idx = typeof nameOrIndex === "number"
      ? nameOrIndex
      : opts.map(function (o) { return o.name; }).indexOf(nameOrIndex);
    var opt = opts[idx];
    if (!opt) return this;
    this._colorActiveIndex = idx;
    this._colorProp = opt.prop || "__rs_fill";
    this._activeLegend = opt.legend || null;
    if (this.fillLayer) this.fillLayer.setStyle(this._fillStyle.bind(this));
    this._refreshLegend();
    this.emit("colorchange", opt, idx);
    return this;
  };

  // Pick the initial active colour option from the spec (called by load() before rendering).
  RoadStyleMap.prototype._initColorState = function () {
    var opts = this.getColorOptions();
    if (opts.length) {
      var i = (this.spec && this.spec.color_active) || 0;
      if (i < 0 || i >= opts.length) i = 0;
      this._colorActiveIndex = i;
      this._colorProp = opts[i].prop || "__rs_fill";
      this._activeLegend = opts[i].legend || (this.spec && this.spec.legend) || null;
    } else {
      this._colorActiveIndex = 0;
      this._colorProp = "__rs_fill";
      this._activeLegend = (this.spec && this.spec.legend) || null;
    }
  };

  // ── Custom panels ─────────────────────────────────────────────────────────────
  // Add a styled, positioned panel and let the caller fill it. `spec`:
  //   { position?: "topleft"|"topright"|"bottomleft"|"bottomright" (default "topright"),
  //     title?, className?, render?(body, map) }
  // Panels sharing a corner stack vertically. Returns { el, body, remove() }.
  RoadStyleMap.prototype.addPanel = function (spec) {
    spec = spec || {};
    var d = L.DomUtil.create("div", "rs-panel" + (spec.className ? " " + spec.className : ""));
    if (spec.title) {
      var h = L.DomUtil.create("h4", "rs-panel-hd", d);
      h.textContent = spec.title;
    }
    var body = L.DomUtil.create("div", "rs-panel-body", d);
    if (L.DomEvent) {
      L.DomEvent.disableClickPropagation(d);
      L.DomEvent.disableScrollPropagation(d);
    }
    this._panelStack(spec.position || "topright").appendChild(d);
    var handle = {
      el: d,
      body: body,
      remove: function () { if (d.parentNode) d.parentNode.removeChild(d); },
    };
    if (typeof spec.render === "function") spec.render(body, this);
    return handle;
  };

  // The flex stack container for a corner (created on first use), so panels never overlap.
  RoadStyleMap.prototype._panelStack = function (position) {
    if (this._panelStacks[position]) return this._panelStacks[position];
    var s = L.DomUtil.create("div", "rs-stack rs-stack-" + position);
    this.map.getContainer().appendChild(s);
    this._panelStacks[position] = s;
    return s;
  };

  // 3-layer neon glow on a selected feature, sized to always sit ON TOP of the edge it covers
  // (so the colour visibly changes even on wide roads). The overlay is non-interactive so a
  // second click on the same edge still reaches it and toggles the selection off.
  RoadStyleMap.prototype.highlightRoad = function (feature) {
    if (this.highlightLayer) this.map.removeLayer(this.highlightLayer);
    var s = this.options.selectionStyle;
    var w = (feature && feature.properties && feature.properties.__rs_w) || 4;
    function lyr(part, weight) {
      return L.geoJSON(feature, {
        interactive: false,
        style: {
          color: part.color,
          weight: weight,
          opacity: part.opacity,
          lineCap: "round",
          lineJoin: "round",
        },
      });
    }
    // featureGroup (not layerGroup) — only FeatureGroup has bringToFront(); a plain layerGroup
    // throws there, which would abort selectFeature before the tooltip gets pinned.
    this.highlightLayer = L.featureGroup([
      lyr(s.glow, Math.max(s.glow.width, w + 10)),
      lyr(s.casing, Math.max(s.casing.width, w + 5)),
      lyr(s.core, Math.max(s.core.width, w + 2)),
    ]).addTo(this.map);
    this.highlightLayer.bringToFront();
  };

  // ── Optional built-in widgets ────────────────────────────────────────────────
  RoadStyleMap.prototype._renderWidgets = function () {
    var w = this.options.widgets || {};
    // Render the legend container if any colour option (or the base spec) carries a legend — so a
    // class→numeric colour switch can reveal a ramp legend that wasn't there at first.
    if (w.legend && this._hasAnyLegend()) this._renderLegend();
    if (w.filter) this._renderFilterPanel();
    if (w.basemap) this._renderBaseMapSwitcher();
    if (w.colors) this._renderColorPicker();
  };

  RoadStyleMap.prototype._renderBaseMapSwitcher = function () {
    var self = this;
    var labels = Object.keys(this.baseLayers || {});
    if (labels.length < 2) return; // nothing to switch between
    L.control.layers(this.baseLayers, null, { collapsed: true, position: "topleft" }).addTo(this.map);
    this.map.on("baselayerchange", function (e) {
      var bm = self.baseMeta[e.name];
      if (!bm) return;
      self.isDark = !!bm.is_dark;
      self._applyBaseMapFx(bm);
      // casing colour depends on base-map darkness; re-style the casing layer in place.
      if (self.casingLayer) self.casingLayer.setStyle(self._casingStyle.bind(self));
    });
  };

  // Is there any legend to show — the base spec's, or one carried by a colour option?
  RoadStyleMap.prototype._hasAnyLegend = function () {
    if (this.spec && this.spec.legend) return true;
    return this.getColorOptions().some(function (o) { return !!o.legend; });
  };

  // Build the inner HTML for a legend object (categorical entries or a continuous ramp).
  RoadStyleMap.prototype._legendHtml = function (lg) {
    if (!lg) return "";
    var html = lg.title ? "<h4>" + lg.title + "</h4>" : "";
    if (lg.kind === "categorical") {
      (lg.entries || []).forEach(function (e) {
        html += '<div class="rs-row"><span class="rs-sw" style="background:' + e[1] + '"></span>' + e[0] + "</div>";
      });
    } else if (lg.kind === "continuous") {
      html +=
        '<div class="rs-bar" style="min-width:140px;background:linear-gradient(90deg,' +
        (lg.ramp || []).join(",") +
        ');"></div><div class="rs-ends"><span>' +
        lg.vmin +
        "</span><span>" +
        lg.vmax +
        "</span></div>";
    }
    return html;
  };

  RoadStyleMap.prototype._renderLegend = function () {
    this._legendEl = L.DomUtil.create("div", "rs-legend");
    this._legendEl.style.left = "14px";
    this._legendEl.style.bottom = "22px";
    this.map.getContainer().appendChild(this._legendEl);
    this._refreshLegend();
  };

  // Repaint the legend for the active colour option (hidden when that option has no legend, e.g.
  // class styling). Called on construction and on every setColorField().
  RoadStyleMap.prototype._refreshLegend = function () {
    if (!this._legendEl) return;
    var lg = this._activeLegend || (this.spec && this.spec.legend);
    var html = this._legendHtml(lg);
    this._legendEl.innerHTML = html;
    this._legendEl.style.display = html ? "" : "none";
  };

  // "Colour by" picker: a dropdown over the spec's color_options that recolours the map client-side.
  RoadStyleMap.prototype._renderColorPicker = function () {
    var self = this;
    var opts = this.getColorOptions();
    if (opts.length < 2) return; // nothing to switch between
    this.addPanel({
      position: "topright",
      title: "Colour by",
      className: "rs-colorpicker",
      render: function (body) {
        var sel = L.DomUtil.create("select", "rs-select", body);
        opts.forEach(function (o, i) {
          var op = document.createElement("option");
          op.value = String(i);
          op.textContent = o.name;
          sel.appendChild(op);
        });
        sel.value = String(self._colorActiveIndex);
        sel.addEventListener("change", function () {
          self.setColorField(parseInt(sel.value, 10));
        });
        // keep the dropdown in sync if the colour option is changed programmatically
        self.on("colorchange", function (opt, idx) { sel.value = String(idx); });
      },
    });
  };

  RoadStyleMap.prototype._renderFilterPanel = function () {
    var self = this;
    var classes = this.getRoadClasses();
    if (!classes.length) return;
    var d = L.DomUtil.create("div", "rs-filter");
    d.style.right = "14px";
    d.style.top = "14px";
    L.DomEvent.disableClickPropagation(d);
    var html = '<h4>Road type</h4>';
    classes.forEach(function (c) {
      html += '<label class="rs-row"><input type="checkbox" value="' + c + '" checked> ' + c + "</label>";
    });
    d.innerHTML = html;
    d.addEventListener("change", function () {
      var active = Array.prototype.slice
        .call(d.querySelectorAll("input:checked"))
        .map(function (cb) { return cb.value; });
      self.setFilter(active);
    });
    this.map.getContainer().appendChild(d);
  };

  // Convenience: build + load in one call.
  function create(containerId, specOrUrl, options, configOrUrl) {
    var m = new RoadStyleMap(containerId, options);
    m.load(specOrUrl, configOrUrl);
    return m;
  }

  return { RoadStyleMap: RoadStyleMap, create: create, version: VERSION };
});
