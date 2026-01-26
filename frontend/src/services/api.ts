import AsyncStorage from '@react-native-async-storage/async-storage';

const BACKEND_URL = process.env.EXPO_PUBLIC_BACKEND_URL || '';

class ApiService {
  private async getHeaders(): Promise<HeadersInit> {
    const token = await AsyncStorage.getItem('session_token');
    return {
      'Content-Type': 'application/json',
      ...(token ? { 'Authorization': `Bearer ${token}` } : {}),
    };
  }

  private async request<T>(endpoint: string, options: RequestInit = {}): Promise<T> {
    const headers = await this.getHeaders();
    const response = await fetch(`${BACKEND_URL}${endpoint}`, {
      ...options,
      headers: { ...headers, ...options.headers },
    });

    if (!response.ok) {
      const error = await response.json().catch(() => ({ detail: 'Request failed' }));
      throw new Error(error.detail || 'Request failed');
    }

    return response.json();
  }

  // News
  async getNews(category?: string, search?: string) {
    const params = new URLSearchParams();
    if (category) params.append('category', category);
    if (search) params.append('search', search);
    return this.request(`/api/news?${params}`);
  }

  async getNewsCategories() {
    return this.request('/api/news/categories');
  }

  // Market Data
  async getCryptoPrices() {
    return this.request('/api/crypto/prices');
  }

  async getCryptoDetail(symbol: string) {
    return this.request(`/api/crypto/${symbol}`);
  }

  async getStockPrices() {
    return this.request('/api/stocks/prices');
  }

  async getStockDetail(symbol: string) {
    return this.request(`/api/stocks/${symbol}`);
  }

  // Daily Decision
  async getDailyDecision() {
    return this.request('/api/decision/today');
  }

  // Simulator
  async executeVirtualTrade(trade: any) {
    return this.request('/api/simulator/trade', {
      method: 'POST',
      body: JSON.stringify(trade),
    });
  }

  async getSimulatorPortfolio() {
    return this.request('/api/simulator/portfolio');
  }

  async getTradeSuggestions(assetType: string = 'crypto') {
    return this.request(`/api/simulator/suggestions?asset_type=${assetType}`);
  }

  // Portfolio
  async addPortfolioTrade(trade: any) {
    return this.request('/api/portfolio/trade', {
      method: 'POST',
      body: JSON.stringify(trade),
    });
  }

  async getPortfolio() {
    return this.request('/api/portfolio');
  }

  async getPortfolioHistory(days: number = 30) {
    return this.request(`/api/portfolio/history?days=${days}`);
  }

  async exportPortfolio() {
    return this.request('/api/portfolio/export');
  }

  // Watchlist
  async addToWatchlist(item: any) {
    return this.request('/api/watchlist', {
      method: 'POST',
      body: JSON.stringify(item),
    });
  }

  async getWatchlist() {
    return this.request('/api/watchlist');
  }

  async removeFromWatchlist(itemId: string) {
    return this.request(`/api/watchlist/${itemId}`, {
      method: 'DELETE',
    });
  }

  // User
  async updateCapital(capital: number) {
    return this.request('/api/user/capital', {
      method: 'PUT',
      body: JSON.stringify({ capital }),
    });
  }

  async getUserSettings() {
    return this.request('/api/user/settings');
  }

  // Education
  async getEducationTips() {
    return this.request('/api/education/tips');
  }
}

export const api = new ApiService();
