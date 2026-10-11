
import { useEffect, useState } from "react";
import api, {
  documentQAApi,
  getApiErrorMessage,
} from "../services/api";
import type { Project } from "../types";
import type { RAGQueryResponse } from "../services/api";

function DocumentQA() {
  const [projects, setProjects] = useState<Project[]>([]);
  const [projectId, setProjectId] = useState("");
  const [question, setQuestion] = useState("");
  const [result, setResult] = useState<RAGQueryResponse | null>(null);
  const [loadingProjects, setLoadingProjects] = useState(true);
  const [asking, setAsking] = useState(false);
  const [error, setError] = useState("");

  useEffect(() => {
    async function loadProjects() {
      try {
        const response = await api.get<Project[]>("/projects");
        setProjects(response.data);
      } catch (err) {
        setError(
          getApiErrorMessage(err, "Unable to load your accessible projects."),
        );
      } finally {
        setLoadingProjects(false);
      }
    }

    void loadProjects();
  }, []);

  async function askQuestion(event: React.FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!projectId || !question.trim()) return;

    setAsking(true);
    setError("");
    setResult(null);

    try {
      const response = await documentQAApi.ask({
        project_id: projectId,
        question: question.trim(),
        limit: 5,
      });
      setResult(response.data);
    } catch (err) {
      setError(
        getApiErrorMessage(
          err,
          "Unable to answer the question. Check the API and Ollama services.",
        ),
      );
    } finally {
      setAsking(false);
    }
  }

  return (
    <>
      <div className="page-heading">
        <div className="eyebrow">Document Intelligence</div>
        <h1>Project Document Q&amp;A</h1>
        <p className="muted">
          Ask questions about indexed project documents and review the evidence
          returned by the retrieval system.
        </p>
      </div>

      <section className="card document-qa-form">
        <form onSubmit={askQuestion}>
          <label>
            Project
            <select
              value={projectId}
              onChange={(event) => {
                setProjectId(event.target.value);
                setResult(null);
              }}
              required
              disabled={loadingProjects || asking}
            >
              <option value="">
                {loadingProjects ? "Loading projects..." : "Select a project"}
              </option>
              {projects.map((project) => (
                <option key={project.id} value={project.id}>
                  {project.code} — {project.name}
                </option>
              ))}
            </select>
          </label>

          <label>
            Your question
            <textarea
              value={question}
              onChange={(event) => setQuestion(event.target.value)}
              placeholder="e.g. What delay events are documented in the project records?"
              minLength={1}
              maxLength={2000}
              rows={4}
              required
              disabled={asking}
            />
          </label>

          <div className="document-qa-actions">
            <span className="muted">
              Answers are generated from retrieved document evidence.
            </span>
            <button type="submit" disabled={asking || !projectId || !question.trim()}>
              {asking ? "Searching documents..." : "Ask question"}
            </button>
          </div>
        </form>
      </section>

      {error && <div className="alert error">{error}</div>}

      {result && (
        <section className="card document-qa-result">
          <div className="section-title">
            <div>
              <div className="eyebrow">Response</div>
              <h2>Answer</h2>
            </div>
            <span
              className={
                result.insufficient_evidence
                  ? "document-qa-status insufficient"
                  : "document-qa-status"
              }
            >
              {result.insufficient_evidence
                ? "Insufficient evidence"
                : "Sources returned"}
            </span>
          </div>

          <p className="document-qa-answer">{result.answer}</p>

          <div className="eyebrow document-qa-source-heading">
            Retrieved sources ({result.sources.length})
          </div>

          {result.sources.length === 0 ? (
            <p className="muted">
              No source chunks were retrieved for this question.
            </p>
          ) : (
            <div className="document-qa-sources">
              {result.sources.map((source, index) => (
                <article className="document-qa-source" key={source.chunk_id}>
                  <h3>[{index + 1}] {source.document_name}</h3>
                  <p className="muted">{source.source_filename}</p>

                  <dl>
                    {source.page_number != null && (
                      <>
                        <dt>Page</dt>
                        <dd>{source.page_number}</dd>
                      </>
                    )}
                    {source.sheet_name && (
                      <>
                        <dt>Sheet</dt>
                        <dd>{source.sheet_name}</dd>
                      </>
                    )}
                    {source.row_start != null && (
                      <>
                        <dt>Rows</dt>
                        <dd>
                          {source.row_start}
                          {source.row_end != null &&
                          source.row_end !== source.row_start
                            ? `–${source.row_end}`
                            : ""}
                        </dd>
                      </>
                    )}
                    {source.section && (
                      <>
                        <dt>Section</dt>
                        <dd>{source.section}</dd>
                      </>
                    )}
                    {source.clause_reference && (
                      <>
                        <dt>Clause</dt>
                        <dd>{source.clause_reference}</dd>
                      </>
                    )}
                  </dl>
                </article>
              ))}
            </div>
          )}

          <p className="muted document-qa-disclaimer">
            Retrieved sources are evidence candidates. Review the original
            documents before relying on an answer for contractual or project
            decisions.
          </p>
        </section>
      )}
    </>
  );
}

export default DocumentQA;
