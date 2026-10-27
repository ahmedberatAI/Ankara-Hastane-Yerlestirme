/** Identical UI contracts, served either by the local API or a sealed Pages bundle. */
export const precomputedPublication = import.meta.env.MODE === "pages";
export const siteBase = import.meta.env.BASE_URL;
type Entry = { file: string; sha256: string; bytes: number };
type Manifest = { format: number; delivery: string; publicationId: string; planId: string;
  sourcePlanSHA256: string; files: Record<string,Entry>; routes: Record<string,Entry> };
let manifestPromise: Promise<Manifest> | null = null;
const fail = (message: string): never => { throw Error(message); };
const hash = (v: unknown): v is string => typeof v === "string" && /^[a-f0-9]{64}$/.test(v);
function entryProblem(entry: Entry) {
  return !entry || typeof entry.file !== "string" || !/^[A-Za-z0-9_./-]+\.json$/.test(entry.file) ||
    entry.file.split("/").some(x => !x || x === "." || x === "..") || !hash(entry.sha256) ||
    !Number.isInteger(entry.bytes) || entry.bytes < 1;
}
async function checkedJson(entry: Entry, signal?: AbortSignal | null) {
  if (entryProblem(entry)) fail("Yayın dosyasının yolu veya kimliği geçersiz.");
  const response = await fetch(siteBase + "publication/" + entry.file,{signal});
  if (!response.ok) fail("Bu yayının veri dosyası yüklenemedi. Sayfayı yenileyin.");
  const bytes = await response.arrayBuffer();
  if (bytes.byteLength !== entry.bytes) fail("Yayın dosyasının boyutu doğrulanamadı.");
  const digest = [...new Uint8Array(await crypto.subtle.digest("SHA-256",bytes))].map(x=>x.toString(16).padStart(2,"0")).join("");
  if(digest !== entry.sha256) fail("Yayın dosyasının kaynak kimliği doğrulanamadı.");
  return JSON.parse(new TextDecoder("utf-8",{fatal:true}).decode(bytes));
}
async function manifest() {
  if (!manifestPromise) manifestPromise = (async () => {
    const response = await fetch(siteBase + "publication/manifest.json",{cache:"no-cache"});
    if (!response.ok) fail("Önceden hesaplanmış yayın paketi bulunamadı.");
    const m = await response.json() as Manifest;
    if (m.format !== 1 || m.delivery !== "precomputed" || !/^permanent-[a-f0-9]{64}$/.test(m.planId) ||
        !/^pages-[a-f0-9]{64}$/.test(m.publicationId) || !hash(m.sourcePlanSHA256) || !m.files || !m.routes)
      fail("Yayın paketinin biçimi doğrulanamadı.");
    if(m.files["/api/permanent-plan"]?.sha256 !== m.sourcePlanSHA256) fail("Yayın ve ortak plan kaydı farklı.");
    return m;
  })();
  return manifestPromise;
}
export function resetPublicationCache() { manifestPromise = null; }
export async function readJson(endpoint: string, init: RequestInit = {}) {
  if(!precomputedPublication) {
    const response = await fetch(endpoint,init);
    const data = await response.json();
    if(!response.ok) throw Error(typeof data.detail === "string" ? data.detail : "Kayıtlı veri şu anda alınamadı.");
    return data;
  }
  const m = await manifest();
  if(endpoint === "/api/permanent-route") {
    if(init.method !== "POST" || typeof init.body !== "string") fail("Güzergâh isteğinin biçimi geçersiz.");
    const request = JSON.parse(init.body as string) as Record<string,string>;
    if(Object.keys(request).sort().join("|") !== "candidateId|demandId|planId|view" || request.planId !== m.planId ||
        !["car","transit"].includes(request.view) || ![request.demandId,request.candidateId].every(v=>typeof v === "string" && /^[A-Za-z0-9_-]+$/.test(v)))
      fail("Güzergâh isteği bu yayındaki planla eşleşmiyor.");
    const entry = m.routes[`${request.view}/${request.demandId}/${request.candidateId}`];
    if(!entry) fail("Bu atamanın güzergâhı yayın paketinde bulunamadı.");
    const record = await checkedJson(entry,init.signal);
    if(record.format !== 1 || record.sourcePlanSHA256 !== m.sourcePlanSHA256 ||
        Object.entries(request).some(([k,v])=>record.request?.[k] !== v) ||
        record.response?.planId !== m.planId || record.response?.routeMode !== request.view)
      fail("Kayıtlı güzergâh başka bir plana ait.");
    return record.response;
  }
  if(init.method && init.method !== "GET") fail("Bu yayın yalnız kayıtlı sonuçları gösterir.");
  const entry = m.files[endpoint];
  if(!entry) fail("İstenen veri bu yayın paketinde bulunmuyor.");
  const value = await checkedJson(entry,init.signal);
  if(endpoint === "/api/permanent-plan" && value.planId !== m.planId) fail("Yayın ve ortak planın kimlikleri farklı.");
  return value;
}
