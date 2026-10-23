import { useEffect, useState } from "react";
import { MapContainer, TileLayer, CircleMarker, Tooltip, GeoJSON, useMap } from "react-leaflet";
import L from "leaflet";
import type { FeatureCollection } from "geojson";
import type { Dataset } from "./types";
import type { JointSite } from "./JointPlan";

const fmt = (n: number) => n.toLocaleString("tr-TR", { maximumFractionDigits: 0 });
function Fit({ sites }: { sites: JointSite[] }) {
  const map = useMap();
  useEffect(() => {
    map.fitBounds(L.latLngBounds(sites.map(s => [s.lat, s.lon])), { padding: [30, 30], animate: false });
    const observer = new ResizeObserver(() => map.invalidateSize({ pan: false }));
    observer.observe(map.getContainer());
    return () => observer.disconnect();
  }, [map, sites]);
  return null;
}

export default function JointPlanMap({ data, sites }: { data: Dataset; sites: JointSite[] }) {
  const [districts, setDistricts] = useState<FeatureCollection | null>(null);
  const [population, setPopulation] = useState(true);
  const [tileFailed, setTileFailed] = useState(false);
  useEffect(() => {
    const controller = new AbortController();
    fetch("/api/layers/districts", { signal: controller.signal }).then(r => r.ok ? r.json() : null).then(setDistricts).catch(() => {});
    return () => controller.abort();
  }, []);
  return <div className="joint-map-content">
    <div className="joint-map-legend"><span><i />Ortak hastane konumu · dört profilde aynı</span>
      <label><input type="checkbox" checked={population} onChange={e => setPopulation(e.target.checked)} /> Nüfus arka planı</label></div>
    <MapContainer center={[39.86, 32.66]} zoom={8} scrollWheelZoom={false} className="joint-map" preferCanvas>
      <TileLayer url="https://tile.openstreetmap.org/{z}/{x}/{y}.png" attribution='&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap contributors</a>' eventHandlers={{ tileerror: () => setTileFailed(true) }} />
      {districts && <GeoJSON data={districts} style={{ color: "#8b9b9d", weight: 1, fillOpacity: .06, dashArray: "4 4" }} />}
      {population && data.demands.map(d => <CircleMarker key={d.id} center={[d.lat, d.lon]} radius={Math.max(2, Math.min(12, Math.sqrt(d.population) / 30))}
        pathOptions={{ color: "#8b9692", fillColor: "#8b9692", fillOpacity: .25, weight: .5 }}>
        <Tooltip>{d.name} · {d.district}<br />{fmt(d.population)} kişi · nüfus arka planı</Tooltip>
      </CircleMarker>)}
      {sites.map(s => <CircleMarker key={s.id} center={[s.lat, s.lon]} radius={Math.min(10, 4 + Math.sqrt(s.beds) / 15)}
        pathOptions={{ color: "#ffffff", fillColor: "#64429a", fillOpacity: .95, weight: 1.5 }}>
        <Tooltip><b>{data.candidates[s.candidateIndex]?.district} · {s.id}</b><br />
          {fmt(s.beds)} yatak · {fmt(s.doctors)} hekim<br />
          Dört profilde en yüksek atama: {fmt(s.maximumAssignedPopulationAcrossProfiles)} kişi eşdeğeri</Tooltip>
      </CircleMarker>)}
      <Fit sites={sites} />
    </MapContainer>
    {tileFailed && <p>Altlık haritası yüklenemedi; doğrulanmış konumlar gösteriliyor.</p>}
    <p className="joint-note">Gri halkalar nüfusu, mor noktalar ortak planı gösterir. Nüfus halkaları kapsama haritası değildir.
      Ayrıntı için yakınlaştırın veya konumun üzerine gelin. Konumlar dört profilde değişmez.</p>
  </div>;
}
