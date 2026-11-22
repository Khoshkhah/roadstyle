// The page script of examples/vehicles/dashboard.html, after the play bar (rust/roadstyle-assets/files/static/vehicles/play_bar.js):
// a time with many vehicles and the example's view. The page loads the run itself, from its option `vehicles`.
rs.ready(async () => {
  await (rs.vehicles.report() || new Promise((r) => document.addEventListener("rs:vehicleload", r, {once: true})));
  rs.vehicles.seek(300);   // a time with many vehicles on the network
  // the page fits the roads first; the example's view after that
  await new Promise((r) => map.loaded() ? r() : map.once("idle", r));
  map.jumpTo({center: [7.4246, 43.7384], zoom: 16.5, pitch: 55, bearing: -20});
});
