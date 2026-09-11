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
  email: string;
  role: string;
};
