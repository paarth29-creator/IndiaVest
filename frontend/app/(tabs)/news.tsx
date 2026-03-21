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
import { InfoButton, GlossaryScreen } from './FinanceTooltip';

const API_URL = process.env.EXPO_PUBLIC_BACKEND_URL || '';

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

interface LeaderStatement {
  id: string;
  leader: string;
  role: string;
  statement: string;
  source: string;
  published_at: string;
  published_ist: string;
  assets_mentioned: string[];
  sentiment_score: number;
  ai_analysis: string;
  impact_history: {
    tracked?: boolean;
    note?: string;
    '1h_change': number | null;
    '24h_change': number | null;
    '7d_change': number | null;
  };
}

const CATEGORY_COLORS: Record<string, string> = {
  world_economies: '#3b82f6',
  geopolitics: '#ef4444',
  india_specific: '#f59e0b',
  crypto_relevant: '#10b981',
  leader_statements: '#8b5cf6',
};

const CATEGORY_LABELS: Record<string, string> = {
  world_economies: 'World',
  geopolitics: 'Geopolitics',
  india_specific: 'India',
  crypto_relevant: 'Crypto/Stock',
  leader_statements: 'Leaders',
};

export default function NewsScreen() {
  const [activeTab, setActiveTab] = useState<'news' | 'leaders'>('news');
  const [news, setNews] = useState<NewsItem[]>([]);
  const [leaders, setLeaders] = useState<LeaderStatement[]>([]);
  const [loading, setLoading] = useState(true);
  const [refreshing, setRefreshing] = useState(false);
  const [selectedCategory, setSelectedCategory] = useState<string | null>(null);
  const [searchQuery, setSearchQuery] = useState('');
  const [expandedNews, setExpandedNews] = useState<string | null>(null);
  const [expandedLeader, setExpandedLeader] = useState<string | null>(null);
  const [editMode, setEditMode] = useState(false);
  const [showGlossary, setShowGlossary] = useState(false);

  useEffect(() => {
    if (activeTab === 'news') {
      fetchNews();
    } else {
      fetchLeaders();
    }

    const interval = setInterval(() => {
      if (activeTab === 'news') {
        fetchNews();
      } else {
        fetchLeaders();
      }
    }, 60000);

    return () => clearInterval(interval);
  }, [activeTab, selectedCategory]);

  const fetchNews = async () => {
    try {
      setLoading(true);
      const params = new URLSearchParams();
      if (selectedCategory) params.append('category', selectedCategory);
      if (searchQuery) params.append('search', searchQuery);
      
      const response = await fetch(`${API_URL}/api/news?${params.toString()}`);
      const data = await response.json();
      setNews(data.news || []);
    } catch (error) {
      console.error('Error fetching news:', error);
    } finally {
      setLoading(false);
    }
  };

  const fetchLeaders = async () => {
    try {
      setLoading(true);
      const response = await fetch(`${API_URL}/api/news/leader-statements?use_ai=false`);
      const data = await response.json();
      setLeaders(data.statements || []);
    } catch (error) {
      console.error('Error fetching leader statements:', error);
    } finally {
      setLoading(false);
    }
  };

  const onRefresh = async () => {
    setRefreshing(true);
    if (activeTab === 'news') {
      await fetchNews();
    } else {
      await fetchLeaders();
    }
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

  const getSentimentColor = (score: number) => {
    if (score > 0.3) return '#10b981';
    if (score < -0.3) return '#ef4444';
    return '#f59e0b';
  };

  const getSentimentLabel = (score: number) => {
    if (score > 0.5) return 'BULLISH';
    if (score > 0.2) return 'POSITIVE';
    if (score < -0.5) return 'BEARISH';
    if (score < -0.2) return 'NEGATIVE';
    return 'NEUTRAL';
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
              {item.impact_level?.toUpperCase() || 'MEDIUM'}
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

  const renderLeaderCard = (stmt: LeaderStatement) => {
    const isExpanded = expandedLeader === stmt.id;
    const sentimentColor = getSentimentColor(stmt.sentiment_score);

    return (
      <TouchableOpacity
        key={stmt.id}
        style={styles.leaderCard}
        onPress={() => setExpandedLeader(isExpanded ? null : stmt.id)}
        activeOpacity={0.8}
      >
        <View style={styles.leaderHeader}>
          <View style={styles.leaderInfo}>
            <View style={styles.leaderAvatar}>
              <Ionicons name="person" size={20} color="#fff" />
            </View>
            <View>
              <Text style={styles.leaderName}>{stmt.leader}</Text>
              <Text style={styles.leaderRole}>{stmt.role}</Text>
            </View>
          </View>
          <View style={[styles.sentimentBadge, { backgroundColor: sentimentColor + '20' }]}>
            <Text style={[styles.sentimentText, { color: sentimentColor }]}>
              {getSentimentLabel(stmt.sentiment_score)}
            </Text>
          </View>
        </View>

        <Text style={styles.statementText}>"{stmt.statement}"</Text>

        <View style={styles.assetTags}>
          {stmt.assets_mentioned.map((asset, idx) => (
            <View key={idx} style={styles.assetTag}>
              <Text style={styles.assetTagText}>{asset}</Text>
            </View>
          ))}
        </View>

        <View style={styles.leaderFooter}>
          <Text style={styles.leaderSource}>{stmt.source}</Text>
          <Text style={styles.leaderTime}>{stmt.published_ist}</Text>
        </View>

        {/* Impact History */}
        <View style={styles.impactHistory}>
          <View style={{ flexDirection: 'row', alignItems: 'center', marginBottom: 8 }}>
            <Text style={styles.impactHistoryTitle}>Price Impact After Statement:</Text>
            <InfoButton termKey="change_24h" size={12} />
          </View>
          {stmt.impact_history?.tracked === false ? (
            <View style={{ alignItems: 'center', paddingVertical: 8 }}>
              <Text style={{ color: '#6b7280', fontSize: 12, textAlign: 'center' }}>
                Impact tracking coming soon. The app needs to collect data over time to show real price changes after statements.
              </Text>
            </View>
          ) : (
            <View style={styles.impactRow}>
              <View style={styles.impactItem}>
                <Text style={styles.impactLabel}>1h</Text>
                <Text style={[
                  styles.impactValue,
                  { color: (stmt.impact_history?.['1h_change'] ?? 0) >= 0 ? '#10b981' : '#ef4444' }
                ]}>
                  {(stmt.impact_history?.['1h_change'] ?? 0) >= 0 ? '+' : ''}{(stmt.impact_history?.['1h_change'] ?? 0).toFixed(2)}%
                </Text>
              </View>
              <View style={styles.impactItem}>
                <Text style={styles.impactLabel}>24h</Text>
                <Text style={[
                  styles.impactValue,
                  { color: (stmt.impact_history?.['24h_change'] ?? 0) >= 0 ? '#10b981' : '#ef4444' }
                ]}>
                  {(stmt.impact_history?.['24h_change'] ?? 0) >= 0 ? '+' : ''}{(stmt.impact_history?.['24h_change'] ?? 0).toFixed(2)}%
                </Text>
              </View>
              <View style={styles.impactItem}>
                <Text style={styles.impactLabel}>7d</Text>
                <Text style={[
                  styles.impactValue,
                  { color: (stmt.impact_history?.['7d_change'] ?? 0) >= 0 ? '#10b981' : '#ef4444' }
                ]}>
                  {(stmt.impact_history?.['7d_change'] ?? 0) >= 0 ? '+' : ''}{(stmt.impact_history?.['7d_change'] ?? 0).toFixed(2)}%
                </Text>
              </View>
            </View>
          )}
        </View>

        {isExpanded && (
          <View style={styles.analysisContainer}>
            <View style={styles.analysisDivider} />
            <View style={styles.analysisHeader}>
              <Ionicons name="sparkles" size={16} color="#8b5cf6" />
              <Text style={[styles.analysisLabel, { color: '#8b5cf6' }]}>AI Impact Analysis</Text>
            </View>
            <Text style={styles.analysisText}>{stmt.ai_analysis}</Text>
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
        <View style={styles.headerTop}>
          <View>
            <Text style={styles.headerTitle}>Market News</Text>
            <Text style={styles.headerSubtitle}>AI-analyzed insights for Indian investors</Text>
          </View>
          <View style={{ flexDirection: 'row', alignItems: 'center', gap: 8 }}>
            <TouchableOpacity 
              style={styles.learnButton}
              onPress={() => setShowGlossary(true)}
            >
              <Ionicons name="book-outline" size={16} color="#f59e0b" />
              <Text style={styles.learnButtonText}>Learn</Text>
            </TouchableOpacity>
            <TouchableOpacity 
              style={[styles.editButton, editMode && styles.editButtonActive]}
              onPress={() => setEditMode(!editMode)}
            >
              <Ionicons name="pencil" size={18} color={editMode ? '#fff' : '#9ca3af'} />
            </TouchableOpacity>
          </View>
        </View>
      </View>

      {/* Finance Glossary Modal */}
      <GlossaryScreen visible={showGlossary} onClose={() => setShowGlossary(false)} />

      {/* Main Tabs */}
      <View style={styles.mainTabs}>
        <TouchableOpacity
          style={[styles.mainTab, activeTab === 'news' && styles.mainTabActive]}
          onPress={() => setActiveTab('news')}
        >
          <Ionicons name="newspaper" size={18} color={activeTab === 'news' ? '#6366f1' : '#6b7280'} />
          <Text style={[styles.mainTabText, activeTab === 'news' && styles.mainTabTextActive]}>News</Text>
        </TouchableOpacity>
        <TouchableOpacity
          style={[styles.mainTab, activeTab === 'leaders' && styles.mainTabActive]}
          onPress={() => setActiveTab('leaders')}
        >
          <Ionicons name="people" size={18} color={activeTab === 'leaders' ? '#8b5cf6' : '#6b7280'} />
          <Text style={[styles.mainTabText, activeTab === 'leaders' && { color: '#8b5cf6' }]}>Leader Statements</Text>
        </TouchableOpacity>
      </View>

      {activeTab === 'news' && (
        <>
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
            {Object.entries(CATEGORY_LABELS).filter(([k]) => k !== 'leader_statements').map(([key, label]) => (
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
        </>
      )}

      {loading ? (
        <View style={styles.loadingContainer}>
          <ActivityIndicator size="large" color="#6366f1" />
          <Text style={styles.loadingText}>
            {activeTab === 'news' ? 'Analyzing news...' : 'Fetching leader statements...'}
          </Text>
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
          {activeTab === 'news' ? (
            <>
              {news.map(renderNewsCard)}
              {news.length === 0 && (
                <View style={styles.emptyState}>
                  <Ionicons name="newspaper-outline" size={48} color="#6b7280" />
                  <Text style={styles.emptyText}>No news found</Text>
                </View>
              )}
            </>
          ) : (
            <>
              <View style={styles.leadersBanner}>
                <Ionicons name="information-circle" size={18} color="#8b5cf6" />
                <Text style={styles.leadersBannerText}>
                  Track statements from Elon Musk, Jerome Powell, RBI Governor, SEC Chair, and more key market movers.
                </Text>
              </View>
              {leaders.map(renderLeaderCard)}
              {leaders.length === 0 && (
                <View style={styles.emptyState}>
                  <Ionicons name="people-outline" size={48} color="#6b7280" />
                  <Text style={styles.emptyText}>No leader statements found</Text>
                </View>
              )}
            </>
          )}

          {/* Disclaimer */}
          <View style={styles.disclaimerCard}>
            <Ionicons name="warning" size={18} color="#f59e0b" />
            <Text style={styles.disclaimerText}>
              This is NOT financial advice. All analyses are AI-generated for educational purposes only. 
              Crypto taxed at 30% VDA in India. Always DYOR and consult a SEBI-registered advisor.
            </Text>
          </View>
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
    paddingBottom: 12,
  },
  headerTop: {
    flexDirection: 'row',
    justifyContent: 'space-between',
    alignItems: 'flex-start',
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
  editButton: {
    padding: 10,
    borderRadius: 12,
    backgroundColor: '#1a1a2e',
  },
  editButtonActive: {
    backgroundColor: '#6366f1',
  },
  learnButton: {
    flexDirection: 'row',
    alignItems: 'center',
    backgroundColor: '#f59e0b15',
    paddingHorizontal: 12,
    paddingVertical: 8,
    borderRadius: 12,
    borderWidth: 1,
    borderColor: '#f59e0b30',
    gap: 4,
  },
  learnButtonText: {
    color: '#f59e0b',
    fontSize: 12,
    fontWeight: '600',
  },
  mainTabs: {
    flexDirection: 'row',
    paddingHorizontal: 20,
    marginBottom: 12,
  },
  mainTab: {
    flex: 1,
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'center',
    paddingVertical: 12,
    backgroundColor: '#1a1a2e',
    marginHorizontal: 4,
    borderRadius: 12,
  },
  mainTabActive: {
    backgroundColor: 'rgba(99, 102, 241, 0.2)',
  },
  mainTabText: {
    color: '#6b7280',
    marginLeft: 8,
    fontWeight: '500',
    fontSize: 14,
  },
  mainTabTextActive: {
    color: '#6366f1',
  },
  searchContainer: {
    paddingHorizontal: 20,
    marginBottom: 12,
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
    paddingTop: 12,
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
  // Leader statements styles
  leadersBanner: {
    flexDirection: 'row',
    alignItems: 'flex-start',
    backgroundColor: 'rgba(139, 92, 246, 0.1)',
    padding: 12,
    borderRadius: 12,
    marginBottom: 16,
  },
  leadersBannerText: {
    color: '#8b5cf6',
    fontSize: 12,
    marginLeft: 8,
    flex: 1,
    lineHeight: 18,
  },
  leaderCard: {
    backgroundColor: '#1a1a2e',
    borderRadius: 16,
    padding: 16,
    marginBottom: 16,
    borderWidth: 1,
    borderColor: '#8b5cf620',
  },
  leaderHeader: {
    flexDirection: 'row',
    justifyContent: 'space-between',
    alignItems: 'flex-start',
    marginBottom: 12,
  },
  leaderInfo: {
    flexDirection: 'row',
    alignItems: 'center',
    flex: 1,
  },
  leaderAvatar: {
    width: 40,
    height: 40,
    borderRadius: 20,
    backgroundColor: '#8b5cf6',
    justifyContent: 'center',
    alignItems: 'center',
    marginRight: 12,
  },
  leaderName: {
    color: '#fff',
    fontSize: 16,
    fontWeight: '600',
  },
  leaderRole: {
    color: '#9ca3af',
    fontSize: 12,
    marginTop: 2,
  },
  sentimentBadge: {
    paddingHorizontal: 10,
    paddingVertical: 4,
    borderRadius: 6,
  },
  sentimentText: {
    fontSize: 11,
    fontWeight: '700',
  },
  statementText: {
    color: '#fff',
    fontSize: 15,
    fontStyle: 'italic',
    lineHeight: 24,
    marginBottom: 12,
  },
  assetTags: {
    flexDirection: 'row',
    flexWrap: 'wrap',
    marginBottom: 12,
  },
  assetTag: {
    backgroundColor: '#2d2d44',
    paddingHorizontal: 10,
    paddingVertical: 4,
    borderRadius: 12,
    marginRight: 8,
    marginBottom: 4,
  },
  assetTagText: {
    color: '#fff',
    fontSize: 11,
    fontWeight: '600',
  },
  leaderFooter: {
    flexDirection: 'row',
    justifyContent: 'space-between',
    marginBottom: 12,
  },
  leaderSource: {
    color: '#6b7280',
    fontSize: 12,
  },
  leaderTime: {
    color: '#6b7280',
    fontSize: 12,
  },
  impactHistory: {
    backgroundColor: '#0f0f23',
    padding: 12,
    borderRadius: 12,
  },
  impactHistoryTitle: {
    color: '#9ca3af',
    fontSize: 11,
    marginBottom: 8,
  },
  impactRow: {
    flexDirection: 'row',
    justifyContent: 'space-around',
  },
  impactItem: {
    alignItems: 'center',
  },
  impactLabel: {
    color: '#6b7280',
    fontSize: 11,
  },
  impactValue: {
    fontSize: 14,
    fontWeight: '600',
    marginTop: 2,
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
  disclaimerCard: {
    flexDirection: 'row',
    alignItems: 'flex-start',
    backgroundColor: 'rgba(245, 158, 11, 0.1)',
    borderRadius: 12,
    padding: 16,
    marginTop: 8,
    marginBottom: 20,
  },
  disclaimerText: {
    color: '#f59e0b',
    fontSize: 11,
    marginLeft: 10,
    flex: 1,
    lineHeight: 16,
  },
});