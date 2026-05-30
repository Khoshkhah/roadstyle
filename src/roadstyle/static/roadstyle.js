/*!
 * roadstyle.js — the ONE canonical browser renderer for the roadstyle `spec/1` format.
 *
 * Single source of truth: the Python library (`roadstyle.emit.to_html`) inlines THIS exact file,
 * and you can also drop it into any page on its own:
 *
 *     <script src="https://unpkg.com/leaflet@1.9.4/dist/leaflet.js"></script>
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
    // Click selection — 3-layer neon-violet glow (glow under, casing, white core on top)
    selectionStyle: {
      glow: { color: "#FF00FF", width: 12, opacity: 0.4 },
      casing: { color: "#000000", width: 7, opacity: 1.0 },
      core: { color: "#FFFFFF", width: 4, opacity: 1.0 },
    },
    // Leaflet map toggles
    doubleClickZoom: true,
    zoomControl: true,
    // Optional built-in UI widgets (opt-in — no front-end code required to get a usable map).
    widgets: {
      legend: true, // render the spec's legend (if present)
      filter: false, // a road-class checkbox panel
      basemap: false, // reserved: a base-map switcher (spec carries a single basemap today)
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
    this.activeFilters = null; // null = show all
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
      var cfgP = configOrUrl ? self.loadInteractionConfig(configOrUrl) : Promise.resolve();
      return cfgP.then(function () {
        self._renderBaseMap();
        self._renderRoads();
        self._renderWidgets();
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
  };

  RoadStyleMap.prototype._visible = function (p) {
    return !this.activeFilters || this.activeFilters.indexOf(p.__rs_class) !== -1;
  };

  RoadStyleMap.prototype._casingStyle = function (f) {
    var p = f.properties;
    if (!p.__rs_casing || !p.__rs_cw) return { opacity: 0, weight: 0 };
    return {
      color: p.__rs_casing,
      weight: p.__rs_cw,
      opacity: this._visible(p) ? p.__rs_cop : 0,
      lineCap: "round",
      lineJoin: "round",
    };
  };

  RoadStyleMap.prototype._fillStyle = function (f) {
    var p = f.properties;
    return {
      color: p.__rs_fill,
      weight: p.__rs_w,
      opacity: this._visible(p) ? p.__rs_op : 0,
      dashArray: p.__rs_dash,
      lineCap: "round",
      lineJoin: "round",
    };
  };

  RoadStyleMap.prototype._renderBaseMap = function () {
    var bm = (this.spec && this.spec.basemap) || {};
    if (bm.url) {
      L.tileLayer(bm.url, {
        attribution: bm.attr || "",
        subdomains: bm.subdomains || "abc",
        maxZoom: 20,
      }).addTo(this.map);
    }
    if (this.spec && this.spec.bounds) this.map.fitBounds(this.spec.bounds);
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
          layer.bindTooltip(
            tip
              .map(function (k) {
                return "<b>" + k + "</b>: " + (ft.properties[k] == null ? "" : ft.properties[k]);
              })
              .join("<br>"),
            { sticky: true }
          );
        }
        layer.on("mouseover", function (e) {
          if (!self._visible(ft.properties)) return;
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
        layer.on("click", function () {
          self.highlightRoad(ft);
        });
      },
    }).addTo(this.map);
  };

  // 3-layer neon-violet glow on a selected feature.
  RoadStyleMap.prototype.highlightRoad = function (feature) {
    if (this.highlightLayer) this.map.removeLayer(this.highlightLayer);
    var s = this.options.selectionStyle;
    function lyr(part) {
      return L.geoJSON(feature, {
        style: { color: part.color, weight: part.width, opacity: part.opacity, lineCap: "round" },
      });
    }
    this.highlightLayer = L.layerGroup([lyr(s.glow), lyr(s.casing), lyr(s.core)]).addTo(this.map);
  };

  // ── Optional built-in widgets ────────────────────────────────────────────────
  RoadStyleMap.prototype._renderWidgets = function () {
    var w = this.options.widgets || {};
    if (w.legend) this._renderLegend();
    if (w.filter) this._renderFilterPanel();
  };

  RoadStyleMap.prototype._renderLegend = function () {
    var lg = this.spec && this.spec.legend;
    if (!lg) return;
    var d = L.DomUtil.create("div", "rs-legend");
    d.style.left = "14px";
    d.style.bottom = "22px";
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
    d.innerHTML = html;
    this.map.getContainer().appendChild(d);
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
