import AgentFlowAssetBundlePageClient from "../../../components/agent-flow-asset-bundle-page-client";

export default async function AgentFlowAssetBundlePage({ params }) {
  const resolvedParams = await params;
  return <AgentFlowAssetBundlePageClient bundleId={resolvedParams.bundleId} />;
}
