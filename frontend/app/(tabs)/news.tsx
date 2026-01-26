import React, { useState, useEffect } from 'react';
import {
  View,
  Text,
  StyleSheet,
  ScrollView,
  TouchableOpacity,
  TextInput,
  ActivityIndicator,
  RefreshControl,
} from 'react-native';
import { SafeAreaView } from 'react-native-safe-area-context';
import { Ionicons } from '@expo/vector-icons';
import { api } from '../../src/services/api';

interface NewsItem {
  id: string;
  title: string;
  source: string;
  category: string;
  published_at: string;
  summary: string;
  impact_level: string;
  ai_analysis: string;
}

const CATEGORY_COLORS: Record<string, string> = {
  world_economies: '#3b82f6',
  geopolitics: '#ef4444',
  india_specific: '#f59e0b',
  crypto_relevant: '#10b981',
};

const CATEGORY_LABELS: Record<string, string> = {
  world_economies: 'World',
  geopolitics: 'Geopolitics',
  india_specific: 'India',
  crypto_relevant: 'Crypto/Stock',
};

export default function NewsScreen() {
  const [news, setNews] = useState<NewsItem[]>([]);
  const [loading, setLoading] = useState(true);
  const [refreshing, setRefreshing] = useState(false);
  const [selectedCategory, setSelectedCategory] = useState<string | null>(null);
  const [searchQuery, setSearchQuery] = useState('');
  const [expandedNews, setExpandedNews] = useState<string | null>(null);

  useEffect(() => {
    fetchNews();
  }, [selectedCategory]);

  const fetchNews = async () => {
    try {
      setLoading(true);
      const response: any = await api.getNews(selectedCategory || undefined, searchQuery || undefined);
      setNews(response.news || []);
    } catch (error) {
      console.error('Error fetching news:', error);
    } finally {
      setLoading(false);
    }
  };

  const onRefresh = async () => {
    setRefreshing(true);
    await fetchNews();
    setRefreshing(false);
  };

  const handleSearch = () => {
    fetchNews();
  };

  const formatDate = (dateStr: string) => {
    const date = new Date(dateStr);
    return date.toLocaleString('en-IN', { 
      timeZone: 'Asia/Kolkata',
      hour: '2-digit',
      minute: '2-digit',
      day: '2-digit',
      month: 'short'
    });
  };

  const renderNewsCard = (item: NewsItem) => {
    const isExpanded = expandedNews === item.id;
    const categoryColor = CATEGORY_COLORS[item.category] || '#6366f1';

    return (
      <TouchableOpacity
        key={item.id}
        style={styles.newsCard}
        onPress={() => setExpandedNews(isExpanded ? null : item.id)}
        activeOpacity={0.8}
      >
        <View style={styles.newsHeader}>
          <View style={[styles.categoryBadge, { backgroundColor: categoryColor + '20' }]}>
            <Text style={[styles.categoryText, { color: categoryColor }]}>
              {CATEGORY_LABELS[item.category] || item.category}
            </Text>
          </View>
          <View style={[styles.impactBadge, { 
            backgroundColor: item.impact_level === 'high' ? '#ef444420' : '#6b728020' 
          }]}>
            <Text style={[styles.impactText, { 
              color: item.impact_level === 'high' ? '#ef4444' : '#6b7280' 
            }]}>
              {item.impact_level.toUpperCase()}
            </Text>
          </View>
        </View>

        <Text style={styles.newsTitle}>{item.title}</Text>
        
        <View style={styles.newsFooter}>
          <Text style={styles.newsSource}>{item.source}</Text>
          <Text style={styles.newsTime}>{formatDate(item.published_at)}</Text>
        </View>

        {isExpanded && (
          <View style={styles.analysisContainer}>
            <View style={styles.analysisDivider} />
            <View style={styles.analysisHeader}>
              <Ionicons name="sparkles" size={16} color="#6366f1" />
              <Text style={styles.analysisLabel}>AI Analysis</Text>
            </View>
            <Text style={styles.analysisText}>{item.ai_analysis}</Text>
          </View>
        )}

        <View style={styles.expandIndicator}>
          <Ionicons 
            name={isExpanded ? 'chevron-up' : 'chevron-down'} 
            size={20} 
            color="#6b7280" 
          />
        </View>
      </TouchableOpacity>
    );
  };

  return (
    <SafeAreaView style={styles.container} edges={['top']}>
      <View style={styles.header}>
        <Text style={styles.headerTitle}>Market News</Text>
        <Text style={styles.headerSubtitle}>AI-analyzed insights for Indian investors</Text>
      </View>

      <View style={styles.searchContainer}>
        <View style={styles.searchBox}>
          <Ionicons name="search" size={20} color="#6b7280" />
          <TextInput
            style={styles.searchInput}
            placeholder="Search news or assets..."
            placeholderTextColor="#6b7280"
            value={searchQuery}
            onChangeText={setSearchQuery}
            onSubmitEditing={handleSearch}
            returnKeyType="search"
          />
          {searchQuery ? (
            <TouchableOpacity onPress={() => { setSearchQuery(''); fetchNews(); }}>
              <Ionicons name="close-circle" size={20} color="#6b7280" />
            </TouchableOpacity>
          ) : null}
        </View>
      </View>

      <ScrollView 
        horizontal 
        showsHorizontalScrollIndicator={false}
        style={styles.categoryScroll}
        contentContainerStyle={styles.categoryContainer}
      >
        <TouchableOpacity
          style={[styles.categoryChip, !selectedCategory && styles.categoryChipActive]}
          onPress={() => setSelectedCategory(null)}
        >
          <Text style={[styles.categoryChipText, !selectedCategory && styles.categoryChipTextActive]}>
            All
          </Text>
        </TouchableOpacity>
        {Object.entries(CATEGORY_LABELS).map(([key, label]) => (
          <TouchableOpacity
            key={key}
            style={[
              styles.categoryChip,
              selectedCategory === key && styles.categoryChipActive,
              { borderColor: CATEGORY_COLORS[key] }
            ]}
            onPress={() => setSelectedCategory(key)}
          >
            <Text style={[
              styles.categoryChipText,
              selectedCategory === key && styles.categoryChipTextActive
            ]}>
              {label}
            </Text>
          </TouchableOpacity>
        ))}
      </ScrollView>

      {loading ? (
        <View style={styles.loadingContainer}>
          <ActivityIndicator size="large" color="#6366f1" />
          <Text style={styles.loadingText}>Analyzing news...</Text>
        </View>
      ) : (
        <ScrollView
          style={styles.newsList}
          contentContainerStyle={styles.newsListContent}
          refreshControl={
            <RefreshControl
              refreshing={refreshing}
              onRefresh={onRefresh}
              tintColor="#6366f1"
            />
          }
        >
          {news.map(renderNewsCard)}
          {news.length === 0 && (
            <View style={styles.emptyState}>
              <Ionicons name="newspaper-outline" size={48} color="#6b7280" />
              <Text style={styles.emptyText}>No news found</Text>
            </View>
          )}
        </ScrollView>
      )}
    </SafeAreaView>
  );
}

const styles = StyleSheet.create({
  container: {
    flex: 1,
    backgroundColor: '#0f0f23',
  },
  header: {
    paddingHorizontal: 20,
    paddingTop: 8,
    paddingBottom: 16,
  },
  headerTitle: {
    fontSize: 28,
    fontWeight: '700',
    color: '#fff',
  },
  headerSubtitle: {
    fontSize: 14,
    color: '#9ca3af',
    marginTop: 4,
  },
  searchContainer: {
    paddingHorizontal: 20,
    marginBottom: 16,
  },
  searchBox: {
    flexDirection: 'row',
    alignItems: 'center',
    backgroundColor: '#1a1a2e',
    borderRadius: 12,
    paddingHorizontal: 16,
    height: 48,
  },
  searchInput: {
    flex: 1,
    color: '#fff',
    fontSize: 16,
    marginLeft: 12,
  },
  categoryScroll: {
    maxHeight: 50,
  },
  categoryContainer: {
    paddingHorizontal: 20,
    gap: 8,
  },
  categoryChip: {
    paddingHorizontal: 16,
    paddingVertical: 8,
    borderRadius: 20,
    backgroundColor: '#1a1a2e',
    marginRight: 8,
  },
  categoryChipActive: {
    backgroundColor: '#6366f1',
  },
  categoryChipText: {
    color: '#9ca3af',
    fontSize: 14,
    fontWeight: '500',
  },
  categoryChipTextActive: {
    color: '#fff',
  },
  loadingContainer: {
    flex: 1,
    justifyContent: 'center',
    alignItems: 'center',
  },
  loadingText: {
    color: '#9ca3af',
    marginTop: 12,
  },
  newsList: {
    flex: 1,
  },
  newsListContent: {
    padding: 20,
    paddingTop: 16,
  },
  newsCard: {
    backgroundColor: '#1a1a2e',
    borderRadius: 16,
    padding: 16,
    marginBottom: 16,
  },
  newsHeader: {
    flexDirection: 'row',
    justifyContent: 'space-between',
    marginBottom: 12,
  },
  categoryBadge: {
    paddingHorizontal: 10,
    paddingVertical: 4,
    borderRadius: 6,
  },
  categoryText: {
    fontSize: 12,
    fontWeight: '600',
  },
  impactBadge: {
    paddingHorizontal: 10,
    paddingVertical: 4,
    borderRadius: 6,
  },
  impactText: {
    fontSize: 11,
    fontWeight: '600',
  },
  newsTitle: {
    fontSize: 16,
    fontWeight: '600',
    color: '#fff',
    lineHeight: 22,
    marginBottom: 12,
  },
  newsFooter: {
    flexDirection: 'row',
    justifyContent: 'space-between',
  },
  newsSource: {
    fontSize: 12,
    color: '#6b7280',
  },
  newsTime: {
    fontSize: 12,
    color: '#6b7280',
  },
  analysisContainer: {
    marginTop: 16,
  },
  analysisDivider: {
    height: 1,
    backgroundColor: '#2d2d44',
    marginBottom: 16,
  },
  analysisHeader: {
    flexDirection: 'row',
    alignItems: 'center',
    marginBottom: 12,
  },
  analysisLabel: {
    color: '#6366f1',
    fontSize: 14,
    fontWeight: '600',
    marginLeft: 8,
  },
  analysisText: {
    color: '#d1d5db',
    fontSize: 14,
    lineHeight: 22,
  },
  expandIndicator: {
    alignItems: 'center',
    marginTop: 8,
  },
  emptyState: {
    flex: 1,
    justifyContent: 'center',
    alignItems: 'center',
    paddingTop: 60,
  },
  emptyText: {
    color: '#6b7280',
    fontSize: 16,
    marginTop: 12,
  },
});
