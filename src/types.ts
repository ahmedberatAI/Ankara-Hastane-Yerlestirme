export type Mode = "car" | "transit";
export type TransitProfile =
  | "weekday-0800"
  | "weekday-1000"
  | "saturday-1000"
  | "sunday-1000";
export const transitProfileLabels: Record<TransitProfile, string> = {
  "weekday-0800": "Hafta içi · 08.00",
  "weekday-1000": "Hafta içi · 10.00",
  "saturday-1000": "Cumartesi · 10.00",
  "sunday-1000": "Pazar · 10.00",
};
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
  transitProfile: TransitProfile;
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
  referenceStage?: {
    hospitalCount: number;
    totalBeds: number;
    totalDoctors: number;
    coveredPopulation: number;
    coveragePercent: number;
    annualEquivalentCostTRY: number;
    meanMinutes: number;
    gap: number | null;
    lowerBoundTRY: number | null;
    boundScope:
      | "all_candidate_allocation_edges"
      | "restricted_allocation_edges";
    scope: string;
  };
  finalPlanCostGap?: number | null;
  numericalFallback?: {
    reason: string;
    rejectedSource: string;
    selectedSource: string;
    rejectedClosedSiteFlowResidents: number;
    allocationAbsoluteDifferenceResidents: number;
    meanMinutesChange: number;
    selectedIncumbentValidated: boolean;
    scope: string;
  } | null;
  optimalityScope?:
    | "all_candidate_allocation_edges"
    | "restricted_allocation_edges";
  resourceCleanup?: {
    applied?: boolean;
    skippedReason?: string | null;
    toleratedClosedSiteFlowResidents?: number;
    beforeHospitalCount: number;
    afterHospitalCount: number;
    removedHospitalCount: number;
    removedBeds: number;
    removedDoctors: number;
    annualCostReductionTRY: number;
    allocationsPreserved: boolean;
    travelPreserved: boolean;
    method: string;
  };
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
    transitPackageId?: string;
    transitDataQuality?: {
      officialRouteCount: number;
      officialStopCount: number;
      routedRouteCount: number;
      coordinateStopCount: number;
      usedDepartures: Record<string, number>;
      officialDepartures: Record<string, number>;
      reviewedServiceEvents?: { appliedCount: number; definedCount: number };
    };
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
  transitEvidence?: { scope: string; packageId: string };
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
  boardings: {
    route: string;
    stop: string;
    mode: string;
    departureTime?: string;
    arrivalTime?: string;
    waitMinutes?: number;
    timingWarning?: string | null;
    timingSourceUrls?: string[];
  }[];
}
