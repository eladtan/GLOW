import assert from 'node:assert/strict';
import { createRequire } from 'node:module';
import test from 'node:test';

const require = createRequire(import.meta.url);
const deployPages = require('../.github/scripts/deploy-pages.js');

function testContext() {
  return {
    repo: { owner: 'eladtan', repo: 'GLOW' },
    sha: 'abc123',
  };
}

function testCore() {
  const outputs = new Map();
  return {
    outputs,
    getIDToken: async () => 'oidc-token',
    info: () => {},
    setOutput: (name, value) => outputs.set(name, value),
    warning: () => {},
  };
}

function setFastEnvironment() {
  process.env.PAGES_ARTIFACT_ID = '42';
  process.env.PAGES_DEPLOY_TIMEOUT_MS = '100';
  process.env.PAGES_DEPLOY_POLL_INTERVAL_MS = '1';
}

test('deploys a Pages artifact and waits for success', async () => {
  setFastEnvironment();
  const core = testCore();
  const calls = [];
  const statuses = ['deployment_queued', 'succeed'];
  const github = {
    request: async (route, parameters) => {
      calls.push({ route, parameters });
      if (route === 'POST /repos/{owner}/{repo}/pages/deployments') {
        return { data: { id: 'deployment-1', page_url: 'https://example.test/' } };
      }
      return { data: { status: statuses.shift() } };
    },
  };

  await deployPages({ github, context: testContext(), core });

  assert.equal(core.outputs.get('page_url'), 'https://example.test/');
  assert.equal(calls[0].parameters.artifact_id, 42);
  assert.equal(calls[0].parameters.pages_build_version, 'abc123');
  assert.equal(calls.at(-1).route, 'GET /repos/{owner}/{repo}/pages/deployments/{deploymentId}');
});

test('reports a terminal Pages deployment failure', async () => {
  setFastEnvironment();
  const github = {
    request: async (route) => {
      if (route === 'POST /repos/{owner}/{repo}/pages/deployments') {
        return { data: { id: 'deployment-2' } };
      }
      return { data: { status: 'deployment_failed' } };
    },
  };

  await assert.rejects(
    deployPages({ github, context: testContext(), core: testCore() }),
    /asked for a later retry/,
  );
});

test('cancels a deployment after the configured timeout', async () => {
  setFastEnvironment();
  process.env.PAGES_DEPLOY_TIMEOUT_MS = '3';
  const calls = [];
  const github = {
    request: async (route) => {
      calls.push(route);
      if (route === 'POST /repos/{owner}/{repo}/pages/deployments') {
        return { data: { id: 'deployment-3' } };
      }
      if (route.endsWith('/cancel')) {
        return { data: {} };
      }
      return { data: { status: 'deployment_queued' } };
    },
  };

  await assert.rejects(
    deployPages({ github, context: testContext(), core: testCore() }),
    /remained pending/,
  );
  assert.ok(calls.some((route) => route.endsWith('/cancel')));
});
