export type Mode = "car" | "transit";
export interface Scenario {
  mode: Mode;
  threshold: number;
  coverageTarget: number;
  districtFloor: number;
  trafficFactor: number;
}
export interface Place {
  id: string;
  name: string;
  district: string;
  districtId: string;
  lon: number;
  lat: number;
  node: number;
}
export interface Demand extends Place {
  population: number;
  snapMeters: number;
  locationMethod: string;
}
export interface Candidate extends Place {
  accessMeters: number;
  footprintRadiusMeters: number;
}
export interface Metrics {
  coveragePercent: number;
  coveredPopulation: number;
  meanMinutes: number | null;
  p90Minutes: number | null;
  unreachableOrUnlocatedPopulation: number;
}
export interface District extends Partial<Metrics> {
  id: string;
  name: string;
  population: number;
  unlistedPopulation: number;
}
export interface Source {
  id: string;
  title: string;
  publisher: string;
  url: string;
  status: string;
  date: string;
  usedFor: string;
  note: string;
}
export interface Dataset {
  demands: Demand[];
  candidates: Candidate[];
  hospitals: Place[];
  districts: District[];
  sources: Source[];
  metadata: {
    provincePopulation: number;
    listedPopulation: number;
    matchedPopulation: number;
    unlocatedPopulation: number;
    neighborhoodCount: number;
    matchedNeighborhoodCount: number;
    candidateCount: number;
    graphNodes: number;
    graphEdges: number;
    osmDate: string;
    source: string;
    transitStatus: string;
    transitRoutes?: number;
    transitStops?: number;
    existingHospitalCount: number;
  };
}
export interface Assignment {
  demandId: string;
  candidateId: string;
  candidateIndex: number;
  minutes: number | null;
  covered: boolean;
}
export interface Result {
  status: "optimal" | "feasible" | "infeasible" | "timeout";
  reason?: string;
  hospitalCount?: number;
  costUnits?: number;
  selected?: Candidate[];
  assignments?: Assignment[];
  metrics?: Metrics;
  districts?: District[];
  gap?: number | null;
  lowerBound?: number | null;
  scenario: Scenario;
  metadata: Dataset["metadata"];
  modelLabel: string;
  existingComparison?: Metrics & { hospitalCount: number };
  maximumCoveragePercent?: number;
  limitingDistricts?: { name: string; maximumPercent: number }[];
  secondaryOptimal?: boolean;
}
export interface Route {
  minutes: number;
  demand: string;
  candidate: string;
  note: string;
  legs: { kind: string; label: string; coordinates: [number, number][] }[];
  boardings: { route: string; stop: string; mode: string }[];
}
