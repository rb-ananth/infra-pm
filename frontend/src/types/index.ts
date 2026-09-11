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