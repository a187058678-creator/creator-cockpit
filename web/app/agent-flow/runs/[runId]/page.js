import AgentFlowRunDetailPageClient from "../../../components/agent-flow-run-detail-page-client";

export default async function AgentFlowRunDetailPage({ params }) {
  const resolvedParams = await params;
  return <AgentFlowRunDetailPageClient runId={resolvedParams.runId} />;
}
