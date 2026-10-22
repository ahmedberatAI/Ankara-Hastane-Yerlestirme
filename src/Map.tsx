import { useEffect, useMemo, useRef, useState } from "react";
import {
  MapContainer,
  TileLayer,
  GeoJSON,
  CircleMarker,
  Marker,
  Tooltip,
  Popup,
  Polyline,
  useMap,
  useMapEvents,
  ZoomControl,
} from "react-leaflet";
import L from "leaflet";
import type { GeoJsonObject, FeatureCollection } from "geojson";
import { LocateFixed, Layers3, Plus } from "lucide-react";
import type { Dataset, Demand, Result, Route, Candidate } from "./types";

const number = (n: number) => n.toLocaleString("tr-TR");
const title = (s: string) =>
  s
    .toLocaleLowerCase("tr-TR")
    .replace(/(^|\s)\S/g, (c) => c.toLocaleUpperCase("tr-TR"));
function MapEffects({
  focus,
  district,
  districts,
  reset,
  route,
}: {
  focus: Candidate | Demand | null;
  district: string;
  districts: FeatureCollection | null;
  reset: number;
  route: Route | null;
}) {
  const map = useMap();
  const first = useRef(true);
  useEffect(() => {
    const mobile = window.matchMedia("(max-width:600px)");
    const update = () => {
      if (mobile.matches) map.scrollWheelZoom.disable();
      else map.scrollWheelZoom.enable();
    };
    update();
    mobile.addEventListener("change", update);
    return () => mobile.removeEventListener("change", update);
  }, [map]);
  useEffect(() => {
    const observer = new ResizeObserver(() => {
      map.invalidateSize({ pan: false });
      if (districts && !focus && !route && !district)
        map.fitBounds(L.geoJSON(districts).getBounds(), {
          padding: [25, 40],
          animate: false,
        });
    });
    observer.observe(map.getContainer());
    return () => observer.disconnect();
  }, [map, districts, focus, route, district]);
  useEffect(() => {
    if (districts && (first.current || reset)) {
      map.fitBounds(L.geoJSON(districts).getBounds(), {
        padding: [25, 40],
        animate: false,
      });
      first.current = false;
    }
  }, [map, districts, reset]);
  useEffect(() => {
    const feature = districts?.features.find(
      (f) => f.properties?.id === district,
    );
    if (feature)
      map.fitBounds(L.geoJSON(feature).getBounds(), {
        padding: [45, 45],
        maxZoom: 12,
      });
  }, [district, districts, map]);
  useEffect(() => {
    if (focus) map.flyTo([focus.lat, focus.lon], 13, { duration: 0.8 });
  }, [focus, map]);
  useEffect(() => {
    const coords = route?.legs.flatMap((l) =>
      l.coordinates.map(([x, y]) => [y, x] as L.LatLngTuple),
    );
    if (coords?.length)
      map.fitBounds(L.latLngBounds(coords), {
        paddingTopLeft: map.getSize().x >= 500 ? [310, 50] : [25, 270],
        paddingBottomRight: map.getSize().x >= 500 ? [35, 80] : [25, 60],
        maxZoom: 14,
      });
  }, [route, map]);
  return null;
}

function SiteMarkers({ sites }: { sites: Candidate[] }) {
  const map = useMap();
  const [zoom, setZoom] = useState(map.getZoom());
  useMapEvents({ zoomend: () => setZoom(map.getZoom()) });
  const groups = useMemo(() => {
    const buckets = new Map<string, { site: Candidate; index: number }[]>();
    sites.forEach((site, index) => {
      const p = map.project([site.lat, site.lon], zoom);
      const key =
        sites.length > 70 && zoom < 14
          ? `${Math.floor(p.x / 48)}:${Math.floor(p.y / 48)}`
          : site.id;
      const bucket = buckets.get(key) || [];
      bucket.push({ site, index });
      buckets.set(key, bucket);
    });
    return [...buckets.values()];
  }, [sites, zoom, map]);
  return (
    <>
      {groups.map((group) => {
        const { site: c, index: i } = group[0];
        if (group.length > 1) {
          const bounds = L.latLngBounds(
            group.map((g) => [g.site.lat, g.site.lon] as L.LatLngTuple),
          );
          return (
            <Marker
              key={`group-${c.id}`}
              position={bounds.getCenter()}
              icon={L.divIcon({
                className: "site-cluster",
                html: `<b>${group.length}</b>`,
                iconSize: [34, 34],
                iconAnchor: [17, 17],
              })}
              eventHandlers={{
                click: () =>
                  map.fitBounds(bounds, {
                    padding: [55, 55],
                    maxZoom: Math.min(16, zoom + 3),
                  }),
              }}
            >
              <Tooltip>{group.length} önerilen hastane · yakınlaştırın</Tooltip>
            </Marker>
          );
        }
        return (
          <Marker
            key={c.id}
            position={[c.lat, c.lon]}
            icon={L.divIcon({
              className: "hospital-marker",
              html: `<span><b>${String(i + 1).padStart(2, "0")}</b></span>`,
              iconSize: [34, 40],
              iconAnchor: [17, 40],
            })}
          >
            <Popup>
              <div className="site-popup">
                <span className="eyebrow">
                  ÖNERİLEN YERLEŞİM {String(i + 1).padStart(2, "0")}
                </span>
                <h3>{title(c.name)}</h3>
                <p>
                  {title(c.district)} · {c.accessMeters.toFixed(0)} m giriş
                  bağlantısı
                </p>
                <small>
                  Yapı alanı yoldan ayrıdır. Binalar engel sayılmamıştır.
                </small>
              </div>
            </Popup>
          </Marker>
        );
      })}
    </>
  );
}

export default function AnkaraMap({
  data,
  result,
  route,
  onDemand,
  focus,
  district,
}: {
  data: Dataset;
  result: Result | null;
  route: Route | null;
  onDemand: (d: Demand) => void;
  focus: Candidate | Demand | null;
  district: string;
}) {
  const [districts, setDistricts] = useState<FeatureCollection | null>(null);
  const [roads, setRoads] = useState<GeoJsonObject | null>(null);
  const [transit, setTransit] = useState<GeoJsonObject | null>(null);
  const [mask, setMask] = useState<GeoJsonObject | null>(null);
  const [population, setPopulation] = useState(true);
  const [existing, setExisting] = useState(false);
  const [network, setNetwork] = useState(false);
  const [layerMenu, setLayerMenu] = useState(false);
  const [reset, setReset] = useState(0);
  const [tileFailed, setTileFailed] = useState(false);
  const assignments = useMemo(
    () => new Map(result?.assignments?.map((a) => [a.demandId, a])),
    [result],
  );
  useEffect(() => {
    const controller = new AbortController();
    for (const [name, setter] of [
      ["districts", setDistricts],
      ["roads", setRoads],
      ["transit-lines", setTransit],
    ] as const) {
      fetch(`/api/layers/${name}`, { signal: controller.signal })
        .then((r) => {
          if (!r.ok) throw Error("Harita katmanı yüklenemedi");
          return r.json();
        })
        .then(setter)
        .catch(() => {});
    }
    fetch("/api/layers/province", { signal: controller.signal })
      .then((r) => r.json())
      .then((f) => {
        const rings =
          f.geometry.type === "MultiPolygon"
            ? f.geometry.coordinates.map((p: number[][][]) => p[0])
            : [f.geometry.coordinates[0]];
        setMask({
          type: "Feature",
          properties: {},
          geometry: {
            type: "Polygon",
            coordinates: [
              [
                [20, 30],
                [45, 30],
                [45, 48],
                [20, 48],
                [20, 30],
              ],
              ...rings,
            ],
          },
        } as GeoJsonObject);
      })
      .catch(() => {});
    return () => controller.abort();
  }, []);
  return (
    <div className="map-wrap">
      <MapContainer
        center={[39.86, 32.66]}
        zoom={8}
        zoomControl={false}
        scrollWheelZoom={false}
        zoomAnimation={false}
        preferCanvas
        className="map"
      >
        <TileLayer
          url="https://tile.openstreetmap.org/{z}/{x}/{y}.png"
          attribution='&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap contributors</a>'
          eventHandlers={{ tileerror: () => setTileFailed(true) }}
        />
        <ZoomControl position="bottomright" />
        {mask && (
          <GeoJSON
            data={mask}
            interactive={false}
            style={{ weight: 0, fillColor: "#f5f7ef", fillOpacity: 0.88 }}
          />
        )}
        {districts && (
          <GeoJSON
            data={districts}
            style={{
              color: "#7c938d",
              weight: 1,
              fillColor: "#dde7d5",
              fillOpacity: 0.1,
              dashArray: "4 5",
            }}
            onEachFeature={(f, layer) =>
              layer.bindTooltip(title(f.properties?.name || ""), {
                sticky: true,
                className: "district-tip",
              })
            }
          />
        )}
        {(network || tileFailed) && roads && (
          <GeoJSON
            data={roads}
            style={{ color: "#c4cbbf", weight: 1, opacity: 0.8 }}
          />
        )}
        {network && transit && (
          <GeoJSON
            data={transit}
            style={{ color: "#6e7eac", weight: 2, opacity: 0.65 }}
          />
        )}
        {population &&
          data.demands.map((d) => {
            const a = assignments.get(d.id);
            const color = a ? (a.covered ? "#3e8772" : "#d88b57") : "#6d8b76";
            return (
              <CircleMarker
                key={d.id}
                center={[d.lat, d.lon]}
                radius={Math.max(
                  2.8,
                  Math.min(10, Math.sqrt(d.population) / 34),
                )}
                pathOptions={{
                  color,
                  weight: 1,
                  fillColor: color,
                  fillOpacity: a?.covered ? 0.4 : 0.55,
                }}
                eventHandlers={{ click: () => onDemand(d) }}
              >
                <Tooltip direction="top">
                  <b>{title(d.name)}</b>
                  <br />
                  {title(d.district)} · {number(d.population)} kişi
                  <br />
                  {a
                    ? a.minutes === null
                      ? "Bu modda bağlantı yok"
                      : `${a.minutes.toFixed(1)} dk · ${a.covered ? "hedef içinde" : "hedef dışında"}`
                    : "Güzergâhı incelemek için seçin"}
                </Tooltip>
              </CircleMarker>
            );
          })}
        {existing &&
          data.hospitals.map((h) => (
            <Marker
              key={h.id}
              position={[h.lat, h.lon]}
              icon={L.divIcon({
                className: "existing-marker",
                html: "+",
                iconSize: [22, 22],
                iconAnchor: [11, 11],
              })}
            >
              <Popup>
                <strong>{h.name}</strong>
                <br />
                Mevcut hastane · OSM envanteri
                <br />
                <small>Tür ve kapasite doğrulanmadı.</small>
              </Popup>
            </Marker>
          ))}
        {result?.selected && <SiteMarkers sites={result.selected} />}
        {route?.legs
          .filter((l) => l.coordinates.length > 1)
          .map((leg, i) => (
            <Polyline
              key={`${i}-${route.demand}`}
              positions={leg.coordinates.map(
                ([x, y]) => [y, x] as L.LatLngTuple,
              )}
              pathOptions={{
                color:
                  leg.kind === "ride"
                    ? "#7662ad"
                    : leg.kind === "drive"
                      ? "#164f43"
                      : "#dd8350",
                weight: leg.kind === "connector" ? 2 : 4,
                dashArray: ["walk", "connector"].includes(leg.kind)
                  ? "5 7"
                  : undefined,
                opacity: 0.95,
              }}
            >
              <Tooltip>{leg.label}</Tooltip>
            </Polyline>
          ))}
        <MapEffects
          focus={focus}
          district={district}
          districts={districts}
          reset={reset}
          route={route}
        />
      </MapContainer>
      <div className="map-heading">
        <span className="live-dot" />
        <div>
          <b>ANKARA</b>
          <span>25 ilçe · ortak bir sağlık ağı</span>
        </div>
      </div>
      <div className="map-tools">
        <button
          className="map-tool"
          onClick={() => setReset((r) => r + 1)}
          title="Ankara’nın tamamını göster"
          aria-label="Ankara’nın tamamını göster"
        >
          <LocateFixed size={19} />
        </button>
        <button
          className={`map-tool ${layerMenu ? "active" : ""}`}
          onClick={() => setLayerMenu(!layerMenu)}
          aria-expanded={layerMenu}
          aria-label="Harita katmanları"
        >
          <Layers3 size={19} />
        </button>
        {layerMenu && (
          <div className="layer-menu">
            <strong>Harita katmanları</strong>
            <label>
              <input
                type="checkbox"
                checked={population}
                onChange={(e) => setPopulation(e.target.checked)}
              />{" "}
              Mahalle nüfusları
            </label>
            <label>
              <input
                type="checkbox"
                checked={existing}
                onChange={(e) => setExisting(e.target.checked)}
              />{" "}
              Mevcut hastaneler
            </label>
            <label>
              <input
                type="checkbox"
                checked={network}
                onChange={(e) => setNetwork(e.target.checked)}
              />{" "}
              Yol ve ulaşım ağı
            </label>
            <small>
              Toplu taşıma çizgileri OSM geometrileridir; tüm hatların aktif
              olduğunu doğrulamaz.
            </small>
          </div>
        )}
      </div>
      <div className="map-legend">
        <span>
          <i className="legend-dot covered" />{" "}
          {result?.metrics ? "Hedef içinde" : "Mahalle nüfusu"}
        </span>
        {result?.metrics && (
          <span>
            <i className="legend-dot uncovered" /> Hedef dışında
          </span>
        )}
        <span>
          <i className="legend-site">
            <Plus size={11} />
          </i>{" "}
          Önerilen hastane
        </span>
        <small>
          Noktalar mahalle nüfusuna göre ölçeklenir.
          {(result?.selected?.length || 0) > 70
            ? " Yakın öneriler gruplandırılır; yakınlaştırın."
            : ""}
        </small>
      </div>
      {tileFailed && (
        <div className="tile-warning">
          Harita altlığı kısmen yüklenemedi. Yerel yol katmanı açık.
        </div>
      )}
    </div>
  );
}
