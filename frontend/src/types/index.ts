export type Project = {
  id: string;
  code: string;
  name: string;
  dept_id: string;
  pm_id: string;
  status: string;
  total_estimated_cost: string;
  start_date: string;
  expected_completion: string;
  created_at: string;
  updated_at: string;
};

export type User = {
  id: string;
  email: string;
  role: string;
  is_active: boolean;
};


export type Contractor = {
  id: string;
  registration_number: string;
  name: string;
  status: string;
  created_at: string;
  updated_at: string;
};


export type Contract = {
  id: string;
  contract_number: string;
  project_id: string;
  contractor_id: string;
  contract_type: string;
  award_date: string;
  contract_value: string;
  start_date: string;
  original_completion_date: string;
  current_completion_date: string;
  status: string;
  created_at: string;
  updated_at: string;
};

export type BoqStatus = "Draft" | "Submitted" | "Approved" | "Superseded";

export type Boq = {
  id: string;
  contract_id: string;
  boq_number: string;
  title: string;
  description: string | null;
  status: BoqStatus;
  created_at: string;
  updated_at: string;
};

export type BoqRevision = {
  id: string;
  boq_id: string;
  revision_number: number;
  revision_date: string;
  status: BoqStatus;
  remarks: string | null;
  created_at: string;
  updated_at: string;
};

export type BoqItem = {
  id: string;
  revision_id: string;
  item_code: string;
  item_number: string;
  description: string;
  unit: string;
  quantity: string;
  rate: string;
  amount: string;
  created_at: string;
  updated_at: string;
};

export type BoqRevisionDetail = {
  boq: Boq;
  revision: BoqRevision;
  items: BoqItem[];
  total: string;
};

export type BoqImportError = {
  row: number | null;
  field: string | null;
  message: string;
};

export type BoqImportPreviewItem = {
  item_code: string;
  item_number: string;
  description: string;
  unit: string;
  quantity: string;
  rate: string;
  amount: string;
};

export type BoqImportPreview = {
  valid: boolean;
  total_rows: number;
  valid_rows: number;
  invalid_rows: number;
  warnings: string[];
  ignored_columns: string[];
  errors: BoqImportError[];
  items: BoqImportPreviewItem[];
};

export type BoqImportResult = {
  revision_id: string;
  imported_count: number;
  created_item_ids: string[];
  total: string;
};

export type MeasurementStatus = "Draft" | "Submitted" | "Approved" | "Rejected";

export type Measurement = {
  id: string;
  boq_item_id: string;
  measurement_date: string;
  quantity: string;
  reference: string;
  description: string;
  remarks: string | null;
  status: MeasurementStatus;
  created_by: string;
  created_at: string;
  updated_at: string;
};

export type MeasurementDetail = {
  measurement: Measurement;
  boq_item: BoqItem;
  cumulative_approved_quantity: string;
  balance_quantity: string;
  percentage_executed: string;
  is_overrun: boolean;
  overrun_quantity: string | null;
};
export type RABillStatus = "Draft" | "Submitted" | "Approved" | "Rejected";

export type RABillDeduction = {
  id: string;
  ra_bill_id: string;
  deduction_type: string;
  description: string | null;
  amount: string;
};

export type RABillItem = {
  id: string;
  ra_bill_id: string;
  boq_item_id: string;
  current_quantity: string;
  rate: string;
  current_amount: string;
  boq_item: BoqItem;
  previous_cumulative_quantity: string;
  cumulative_quantity: string;
  balance_quantity: string;
  cumulative_amount: string;
  previous_cumulative_amount?: string;
  percentage_executed: string;
  measurements: Measurement[];
};

export type RABill = {
  id: string;
  contract_id: string;
  bill_number: string;
  bill_date: string;
  period_from: string;
  period_to: string;
  remarks: string | null;
  status: RABillStatus;
  gross_amount: string;
  deductions_amount: string;
  net_payable: string;
  created_by: string;
  created_at: string;
  updated_at: string;
};

export type RABillDetail = RABill & {
  items: RABillItem[];
  deductions: RABillDeduction[];
};

export type EVMStatus = "Draft" | "Approved" | "Superseded";

export type EVMBaselinePeriod = {
  id: string;
  baseline_id: string;
  period_date: string;
  planned_percentage: string;
  planned_value: string;
  created_at: string;
  updated_at: string;
};

export type EVMBaseline = {
  id: string;
  project_id: string;
  baseline_number: string;
  name: string;
  status: EVMStatus;
  effective_date: string;
  remarks: string | null;
  created_by: string;
  created_at: string;
  updated_at: string;
  periods?: EVMBaselinePeriod[];
};

export type EVMResponse = {
  project_id: string;
  as_of_date: string;
  baseline_id: string | null;
  pv: string;
  ev: string;
  ac: string;
  sv: string;
  cv: string;
  spi: string | null;
  cpi: string | null;
  planned_percentage: string;
  actual_percentage: string;
  schedule_status: string;
  cost_status: string;
};

export type EVMTrendPoint = {
  date: string;
  pv: string;
  ev: string;
  ac: string;
  sv: string;
  cv: string;
  spi: string | null;
  cpi: string | null;
};
