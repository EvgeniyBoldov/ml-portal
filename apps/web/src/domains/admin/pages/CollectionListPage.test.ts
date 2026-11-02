import { afterEach, describe, expect, it, vi } from 'vitest';
import { collectionsApi, type Collection, type CollectionListResponse } from '@/shared/api/collections';
import { fetchAllCollections } from './CollectionListPage';

function createPage(total: number, items: Collection[]): CollectionListResponse {
  return { total, items };
}

describe('fetchAllCollections', () => {
  afterEach(() => vi.restoreAllMocks());

  it('loads every page before returning results for global table filters and sorting', async () => {
    const firstPage = Array.from({ length: 100 }, (_, index) => ({ id: `collection-${index}` }) as Collection);
    const lastItem = { id: 'collection-100' } as Collection;
    const listAll = vi.spyOn(collectionsApi, 'listAll')
      .mockResolvedValueOnce(createPage(101, firstPage))
      .mockResolvedValueOnce(createPage(101, [lastItem]));

    const result = await fetchAllCollections('network');

    expect(result).toHaveLength(101);
    expect(listAll).toHaveBeenNthCalledWith(1, {
      page: 1,
      size: 100,
      include_deprecated: true,
      search: 'network',
    });
    expect(listAll).toHaveBeenNthCalledWith(2, {
      page: 2,
      size: 100,
      include_deprecated: true,
      search: 'network',
    });
  });

  it('rejects instead of returning a partial collection list when a page fails', async () => {
    vi.spyOn(collectionsApi, 'listAll')
      .mockResolvedValueOnce(createPage(101, [{ id: 'collection-1' } as Collection]))
      .mockRejectedValueOnce(new Error('page request failed'));

    await expect(fetchAllCollections('')).rejects.toThrow('page request failed');
  });
});
