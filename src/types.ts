export type Mode = "car" | "transit";
export interface Scenario {
  mode: Mode;
  threshold: number;
  coverageTarget: number;
  districtFloor: number;
  trafficFactor: number;
  demandMultiplier: number;
  bedOccupancy: number;
  contactsPerDoctor: number;
  costTolerance: number;
  hospitalLimit: number | null;
  operatingCostMultiplier: number;
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
  beds?: number;
  doctors?: number;
  templateLabel?: string;
  constructionCostTRY?: number;
  assignedPopulation?: number;
  annualVisits?: number;
  annualBedDays?: number;
  contactCapacity?: number;
  annualContacts?: number;
  annualOperatingCostTRY?: number;
  annualEquivalentCostTRY?: number;
  bedDayCapacity?: number;
  doctorUtilizationPercent?: number;
  bedUtilizationPercent?: number;
  physicalOccupancyPercent?: number;
}
export interface HealthPlanning {
  version: string;
  referenceYear: number;
  defaults: { contactsPerDoctor: number };
  calibration: {
    hospitalExamples: {
      name: string;
      beds: number;
      physicians?: number;
      grossAreaM2?: number;
      outpatientVisits?: number;
      admissions?: number;
    }[];
    contactsPerDoctorObserved: number;
    universityContactsPerDoctorObserved: number;
    scopeNote: string;
  };
  economics: {
    priceBase: string;
    horizonYears: number;
    realDiscountRate: number;
    annualDoctorCostTRY: number;
    annualBedSupportCostTRY: number;
    costPerContactTRY: number;
    annualFixedSiteCostTRY: number;
  };
  observed: {
    population: number;
    hospitalCount: number;
    beds: number;
    physicians: number;
    secondaryTertiaryVisits: number;
    admissions: number;
    bedDays: number;
    occupancyPercent: number;
  };
  rates: {
    visitsPerResident: number;
    admissionsPerResident: number;
    bedDaysPerResident: number;
    lengthOfStayDays: number;
    contactsPerResident: number;
  };
  templates: {
    id: string;
    label: string;
    beds: number;
    grossAreaM2: number;
    unitCostTRY: number;
    constructionCostTRY: number;
  }[];
  assumptions: string[];
  sources: {
    id: string;
    title: string;
    url: string;
    note?: string;
    verifiedCopyUrl?: string;
  }[];
}
export interface CapacitySummary {
  totalBeds: number;
  totalDoctors: number;
  constructionCostTRY: number;
  annualOperatingCostTRY: number;
  annualEquivalentCostTRY: number;
  lifecyclePresentCostTRY: number;
  priceBase: string;
  annualContactsDemand: number;
  annualContactsServed: number;
  referenceCostTRY: number;
  budgetLimitTRY: number;
  referenceMeanMinutes: number;
  travelImprovementPercent: number;
  annualVisitsDemand: number;
  annualVisitsServed: number;
  annualAdmissionsDemand: number;
  annualBedDaysDemand: number;
  annualBedDaysServed: number;
  doctorUtilizationPercent: number;
  bedUtilizationPercent: number;
  costStageGap: number;
  costStageProvenOptimal: boolean;
  travelStageGap: number | null;
  travelStageImproved: boolean;
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
  healthPlanning: HealthPlanning;
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
  candidateId: string | null;
  candidateIndex: number | null;
  minutes: number | null;
  covered: boolean;
  servedFraction: number;
  allocations: {
    candidateId: string;
    candidateIndex: number;
    population: number;
    fraction: number;
    minutes: number;
  }[];
}
export interface Result {
  status: "optimal" | "feasible" | "infeasible" | "timeout" | "inconclusive";
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
  capacity?: CapacitySummary;
  geographicCertificate?: {
    minimumCountLowerBound: number | null;
    fullCandidateCount: number;
    scope: string;
  };
  searchScope?: {
    nearestCandidatesPerFootprintClass: number;
    candidateCount: number;
    allocationEdges: number;
  };
}
export interface Route {
  minutes: number;
  demand: string;
  candidate: string;
  note: string;
  legs: { kind: string; label: string; coordinates: [number, number][] }[];
  boardings: { route: string; stop: string; mode: string }[];
}
