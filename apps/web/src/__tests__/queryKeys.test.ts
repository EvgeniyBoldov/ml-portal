import { describe, it, expect } from 'vitest';
import { qk } from '@shared/api/keys';

describe('Query Keys (qk)', () => {
  describe('rag', () => {
    it('should generate all key', () => {
      expect(qk.rag.all()).toEqual(['rag']);
    });

    it('should generate list key without params', () => {
      expect(qk.rag.list()).toEqual(['rag', 'list', undefined]);
    });

    it('should generate list key with params', () => {
      expect(qk.rag.list({ page: 1, size: 20 })).toEqual([
        'rag',
        'list',
        { page: 1, size: 20 },
      ]);
    });

    it('should generate list key with all params', () => {
      expect(qk.rag.list({ page: 2, size: 50, status: 'ready', q: 'search' })).toEqual([
        'rag',
        'list',
        { page: 2, size: 50, status: 'ready', q: 'search' },
      ]);
    });

    it('should generate detail key', () => {
      expect(qk.rag.detail('doc-123')).toEqual(['rag', 'detail', 'doc-123']);
    });

    it('should generate statusGraph key', () => {
      expect(qk.rag.statusGraph('doc-456')).toEqual(['rag', 'status-graph', 'doc-456']);
    });
  });

  describe('admin.users', () => {
    it('should generate all key', () => {
      expect(qk.admin.users.all()).toEqual(['admin', 'users']);
    });

    it('should generate list key', () => {
      expect(qk.admin.users.list()).toEqual(['admin', 'users', 'list', undefined]);
    });

    it('should generate list key with params', () => {
      expect(qk.admin.users.list({ page: 1, q: 'john', limit: 10 })).toEqual([
        'admin',
        'users',
        'list',
        { page: 1, q: 'john', limit: 10 },
      ]);
    });

    it('should generate detail key', () => {
      expect(qk.admin.users.detail('user-123')).toEqual(['admin', 'users', 'user-123']);
    });
  });

  describe('admin.tenants', () => {
    it('should generate all key', () => {
      expect(qk.admin.tenants.all()).toEqual(['admin', 'tenants']);
    });

    it('should generate list key', () => {
      expect(qk.admin.tenants.list({ page: 2 })).toEqual([
        'admin',
        'tenants',
        'list',
        { page: 2 },
      ]);
    });

    it('should generate detail key', () => {
      expect(qk.admin.tenants.detail('tenant-abc')).toEqual(['admin', 'tenants', 'tenant-abc']);
    });
  });

  describe('admin.models', () => {
    it('should generate all key', () => {
      expect(qk.admin.models.all()).toEqual(['admin', 'models']);
    });

    it('should generate list key', () => {
      expect(qk.admin.models.list({ page: 1, size: 50 })).toEqual([
        'admin',
        'models',
        'list',
        { page: 1, size: 50 },
      ]);
    });

    it('should generate detail key', () => {
      expect(qk.admin.models.detail('model-xyz')).toEqual(['admin', 'models', 'model-xyz']);
    });
  });

  describe('admin.audit', () => {
    it('should generate audit key', () => {
      expect(qk.admin.audit({ page: 1 })).toEqual(['admin', 'audit', { page: 1 }]);
    });
  });

  describe('agents', () => {
    it('should generate all key', () => {
      expect(qk.agents.all()).toEqual(['agents']);
    });

    it('should generate list key', () => {
      expect(qk.agents.list({ q: 'chat' })).toEqual(['agents', 'list', { q: 'chat' }]);
    });

    it('should generate detail key', () => {
      expect(qk.agents.detail('chat-simple')).toEqual(['agents', 'detail', 'chat-simple']);
    });
  });

  describe('prompts', () => {
    it('should generate all key', () => {
      expect(qk.prompts.all()).toEqual(['prompts']);
    });

    it('should generate list key with type filter', () => {
      expect(qk.prompts.list({ type: 'system' })).toEqual([
        'prompts',
        'list',
        { type: 'system' },
      ]);
    });

    it('should generate detail key', () => {
      expect(qk.prompts.detail('system-prompt-v1')).toEqual([
        'prompts',
        'detail',
        'system-prompt-v1',
      ]);
    });
  });

  describe('tools', () => {
    it('should generate all key', () => {
      expect(qk.tools.all()).toEqual(['tools']);
    });

    it('should generate list key', () => {
      expect(qk.tools.list({ q: 'rag' })).toEqual(['tools', 'list', { q: 'rag' }]);
    });

    it('should generate detail key', () => {
      expect(qk.tools.detail('rag.search')).toEqual(['tools', 'detail', 'rag.search']);
    });
  });

  describe('chats', () => {
    it('should generate all key', () => {
      expect(qk.chats.all()).toEqual(['chats']);
    });

    it('should generate list key', () => {
      expect(qk.chats.list('search term')).toEqual(['chats', 'list', 'search term']);
    });

    it('should generate detail key', () => {
      expect(qk.chats.detail('chat-123')).toEqual(['chats', 'detail', 'chat-123']);
    });

    it('should generate messages key', () => {
      expect(qk.chats.messages('chat-456')).toEqual(['chats', 'messages', 'chat-456']);
    });
  });

  describe('auth', () => {
    it('should generate me key', () => {
      expect(qk.auth.me()).toEqual(['auth', 'me']);
    });
  });

  describe('key uniqueness', () => {
    it('should generate unique keys for different resources', () => {
      const ragList = qk.rag.list({ page: 1 });
      const usersList = qk.admin.users.list({ page: 1 });
      const tenantsList = qk.admin.tenants.list({ page: 1 });

      expect(ragList).not.toEqual(usersList);
      expect(usersList).not.toEqual(tenantsList);
      expect(ragList).not.toEqual(tenantsList);
    });

    it('should generate unique keys for different params', () => {
      const page1 = qk.rag.list({ page: 1 });
      const page2 = qk.rag.list({ page: 2 });

      expect(page1).not.toEqual(page2);
    });

    it('should generate same key for same params', () => {
      const key1 = qk.rag.list({ page: 1, size: 20 });
      const key2 = qk.rag.list({ page: 1, size: 20 });

      expect(key1).toEqual(key2);
    });
  });
});
