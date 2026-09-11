export type Project = {
  id: string;
  code: string;
  name: string;
  status: string;
  total_estimated_cost: string;
  start_date: string;
  expected_completion: string;
};

export type User = {
  id: string;
  email: string;
  role: string;
  is_active: boolean;
};
