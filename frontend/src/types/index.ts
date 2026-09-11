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