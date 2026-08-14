/**
 * Search service for full-text search
 */

import { SearchQuery, SearchResult } from './types';

export class SearchService {
  private indexName: string;
  private client: any;

  constructor(indexName: string, client: any) {
    this.indexName = indexName;
    this.client = client;
  }

  /**
   * Perform a search query
   */
  async search<T>(query: SearchQuery): Promise<SearchResult<T>> {
    const { q, page = 1, pageSize = 20, sort = 'relevance', filters = {} } = query;

    const searchParams = {
      index: this.indexName,
      body: {
        query: {
          multi_match: {
            query: q,
            fields: ['title^2', 'body', 'tags'],
            type: 'best_fields'
          }
        },
        from: (page - 1) * pageSize,
        size: pageSize,
        sort: this.buildSortClause(sort)
      }
    };

    // Apply filters
    if (Object.keys(filters).length > 0) {
      searchParams.body.query = {
        bool: {
          must: searchParams.body.query,
          filter: this.buildFilterClauses(filters)
        }
      };
    }

    const response = await this.client.search(searchParams);

    return {
      items: response.hits.hits.map((hit: any) => hit._source),
      total: response.hits.total.value,
      page,
      pageSize,
      hasMore: (page * pageSize) < response.hits.total.value
    };
  }

  /**
   * Build sort clause based on sort parameter
   */
  private buildSortClause(sort: string): any[] {
    switch (sort) {
      case 'date':
        return [{ createdAt: { order: 'desc' } }];
      case 'popularity':
        return [{ _score: { order: 'desc' } }, { views: { order: 'desc' } }];
      case 'relevance':
      default:
        return [{ _score: { order: 'desc' } }];
    }
  }

  /**
   * Build filter clauses from filters object
   */
  private buildFilterClauses(filters: Record<string, any>): any[] {
    return Object.entries(filters).map(([key, value]) => ({
      term: { [key]: value }
    }));
  }

  /**
   * Index a document
   */
  async indexDocument(id: string, document: any): Promise<void> {
    await this.client.index({
      index: this.indexName,
      id,
      body: document
    });
  }

  /**
   * Delete a document
   */
  async deleteDocument(id: string): Promise<void> {
    await this.client.delete({
      index: this.indexName,
      id
    });
  }
}
