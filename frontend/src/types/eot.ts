export interface EOTApplication {
  id: string;
  contract_id: string;
  application_number: string;
  event_date: string;
  notice_date: string;
  submission_date: string | null;
  cause_of_delay: string;
  claimed_days: number;
  approved_days: number | null;
  status: string;
  decision_maker_id: string | null;
  decision_date: string | null;
  decision_reason: string | null;
  previous_completion_date: string | null;
  revised_completion_date: string | null;
  created_by: string;
  created_at: string;
  updated_at: string;
}

export interface EOTApplicationCreate {
  contract_id: string;
  application_number: string;
  event_date: string;
  notice_date: string;
  cause_of_delay: string;
  claimed_days: number;
}

export interface EOTApplicationUpdate {
  event_date?: string;
  notice_date?: string;
  cause_of_delay?: string;
  claimed_days?: number;
}

export interface EOTApplicationDecision {
  approved_days?: number;
  decision_reason: string;
}
