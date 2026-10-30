// A number tile of a page (docs/guides/dashboard-panel.md): `rs.kpi(title, value, sub, color?)` is the HTML of one tile - a small title, a big number and
// a line under it - for a `<div class="rs-kpis">` (a grid of three). The words are HTML of the page's own; the colour of the number is a CSS colour.
const _kpColor = /^[#a-zA-Z0-9(),.% -]+$/;
export const rsKpi = (title, value, sub, color) =>
  '<div class="rs-kpi"><div class="rs-kpi-title">' + title + '</div><div class="rs-kpi-val"' +
  (color && _kpColor.test(color) ? ' style="color:' + color + '"' : "") + ">" + value + '</div><div class="rs-kpi-sub">' + (sub || "") + "</div></div>";
