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
