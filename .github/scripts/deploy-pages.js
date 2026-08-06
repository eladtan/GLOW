'use strict';

const FINAL_ERROR_MESSAGES = {
  deployment_failed: 'Deployment failed; GitHub Pages asked for a later retry.',
  deployment_content_failed: 'GitHub Pages rejected the artifact contents.',
  deployment_cancelled: 'GitHub Pages cancelled the deployment.',
  deployment_lost: 'GitHub Pages lost the deployment status.',
};

const DEFAULT_TIMEOUT_MS = 30 * 60 * 1000;
const DEFAULT_POLL_INTERVAL_MS = 5 * 1000;
const MAX_STATUS_ERRORS = 10;

function positiveInteger(value, fallback) {
  const parsed = Number(value);
  return Number.isInteger(parsed) && parsed > 0 ? parsed : fallback;
}

function wait(milliseconds) {
  return new Promise((resolve) => setTimeout(resolve, milliseconds));
}

async function cancelDeployment(github, context, deploymentId, core) {
  try {
    await github.request(
      'POST /repos/{owner}/{repo}/pages/deployments/{deploymentId}/cancel',
      {
        owner: context.repo.owner,
        repo: context.repo.repo,
        deploymentId,
      },
    );
  } catch (error) {
    core.warning(`Unable to cancel timed-out Pages deployment: ${error.message}`);
  }
}

module.exports = async function deployPages({ github, context, core }) {
  const artifactId = positiveInteger(process.env.PAGES_ARTIFACT_ID, 0);
  if (!artifactId) {
    throw new Error('PAGES_ARTIFACT_ID must identify the uploaded Pages artifact.');
  }

  const timeoutMs = positiveInteger(
    process.env.PAGES_DEPLOY_TIMEOUT_MS,
    DEFAULT_TIMEOUT_MS,
  );
  const pollIntervalMs = positiveInteger(
    process.env.PAGES_DEPLOY_POLL_INTERVAL_MS,
    DEFAULT_POLL_INTERVAL_MS,
  );

  const idToken = await core.getIDToken();
  const created = await github.request(
    'POST /repos/{owner}/{repo}/pages/deployments',
    {
      owner: context.repo.owner,
      repo: context.repo.repo,
      artifact_id: artifactId,
      pages_build_version: context.sha,
      oidc_token: idToken,
    },
  );

  const deployment = created.data;
  const deploymentId = deployment.id || context.sha;
  core.setOutput('page_url', deployment.page_url || '');
  core.info(`Created Pages deployment ${deploymentId}.`);

  const startedAt = Date.now();
  let statusErrors = 0;

  while (Date.now() - startedAt < timeoutMs) {
    await wait(pollIntervalMs);

    let statusResponse;
    try {
      statusResponse = await github.request(
        'GET /repos/{owner}/{repo}/pages/deployments/{deploymentId}',
        {
          owner: context.repo.owner,
          repo: context.repo.repo,
          deploymentId,
        },
      );
      statusErrors = 0;
    } catch (error) {
      statusErrors += 1;
      core.warning(
        `Pages status request ${statusErrors}/${MAX_STATUS_ERRORS} failed: ${error.message}`,
      );
      if (statusErrors >= MAX_STATUS_ERRORS) {
        throw error;
      }
      continue;
    }

    const status = statusResponse.data.status;
    core.info(`Current status: ${status}`);

    if (status === 'succeed') {
      core.info('GitHub Pages deployment succeeded.');
      return;
    }

    if (FINAL_ERROR_MESSAGES[status]) {
      throw new Error(FINAL_ERROR_MESSAGES[status]);
    }
  }

  await cancelDeployment(github, context, deploymentId, core);
  throw new Error(`GitHub Pages remained pending for ${timeoutMs} ms.`);
};
