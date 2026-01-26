import React, { useState, useEffect } from 'react';
import {
  View,
  Text,
  StyleSheet,
  ScrollView,
  TouchableOpacity,
  ActivityIndicator,
  RefreshControl,
} from 'react-native';
import { SafeAreaView } from 'react-native-safe-area-context';
import { Ionicons } from '@expo/vector-icons';
import { api } from '../../src/services/api';

interface Decision {
  recommendation: string;
  confidence: number;
  reasoning: string;
  allocations: {
    crypto?: Record<string, number>;
    stocks?: Record<string, number>;
  };
  risks: string[];
  timeline: string;
}

interface MarketSnapshot {
  btc_price: number;
  btc_rsi: number;
  btc_change: number;
  eth_price: number;
  eth_rsi: number;
  eth_change: number;
  nifty_level: number;
  nifty_change: number;
  inr_usd: number;
}

const RECOMMENDATION_COLORS: Record<string, string> = {
  Crypto: '#10b981',
  Stocks: '#3b82f6',
  Both: '#8b5cf6',
  Hold: '#f59e0b',
};

const RECOMMENDATION_ICONS: Record<string, string> = {
  Crypto: 'logo-bitcoin',
  Stocks: 'trending-up',
  Both: 'git-branch',
  Hold: 'pause-circle',
};

export default function DecisionScreen() {
  const [decision, setDecision] = useState<Decision | null>(null);
  const [marketSnapshot, setMarketSnapshot] = useState<MarketSnapshot | null>(null);
  const [loading, setLoading] = useState(true);
  const [refreshing, setRefreshing] = useState(false);
  const [date, setDate] = useState('');
  const [timeIst, setTimeIst] = useState('');

  useEffect(() => {
    fetchDecision();
  }, []);

  const fetchDecision = async () => {
    try {
      setLoading(true);
      const response: any = await api.getDailyDecision();
      setDecision(response.decision);
      setMarketSnapshot(response.market_snapshot);
      setDate(response.date);
      setTimeIst(response.time_ist);
    } catch (error) {
      console.error('Error fetching decision:', error);
    } finally {
      setLoading(false);
    }
  };

  const onRefresh = async () => {
    setRefreshing(true);
    await fetchDecision();
    setRefreshing(false);
  };

  const formatCurrency = (value: number) => {
    return new Intl.NumberFormat('en-IN', {
      style: 'currency',
      currency: 'INR',
      maximumFractionDigits: 0,
    }).format(value);
  };

  if (loading) {
    return (
      <SafeAreaView style={styles.container} edges={['top']}>
        <View style={styles.loadingContainer}>
          <ActivityIndicator size="large" color="#6366f1" />
          <Text style={styles.loadingText}>Analyzing markets...</Text>
        </View>
      </SafeAreaView>
    );
  }

  const recommendationColor = RECOMMENDATION_COLORS[decision?.recommendation || 'Hold'];
  const recommendationIcon = RECOMMENDATION_ICONS[decision?.recommendation || 'Hold'];

  return (
    <SafeAreaView style={styles.container} edges={['top']}>
      <ScrollView
        style={styles.scrollView}
        contentContainerStyle={styles.content}
        refreshControl={
          <RefreshControl refreshing={refreshing} onRefresh={onRefresh} tintColor="#6366f1" />
        }
      >
        <View style={styles.header}>
          <Text style={styles.headerTitle}>Daily Decision</Text>
          <Text style={styles.headerSubtitle}>{date} • {timeIst}</Text>
        </View>

        {/* Main Recommendation Card */}
        <View style={[styles.recommendationCard, { borderColor: recommendationColor }]}>
          <View style={styles.recommendationHeader}>
            <View style={[styles.recommendationIcon, { backgroundColor: recommendationColor + '20' }]}>
              <Ionicons name={recommendationIcon as any} size={32} color={recommendationColor} />
            </View>
            <View style={styles.recommendationInfo}>
              <Text style={styles.recommendationLabel}>TODAY'S RECOMMENDATION</Text>
              <Text style={[styles.recommendationValue, { color: recommendationColor }]}>
                {decision?.recommendation}
              </Text>
            </View>
          </View>
          <View style={styles.confidenceBar}>
            <View style={styles.confidenceLabel}>
              <Text style={styles.confidenceText}>Confidence</Text>
              <Text style={styles.confidenceValue}>{decision?.confidence}%</Text>
            </View>
            <View style={styles.confidenceTrack}>
              <View 
                style={[
                  styles.confidenceFill, 
                  { width: `${decision?.confidence || 0}%`, backgroundColor: recommendationColor }
                ]} 
              />
            </View>
          </View>
        </View>

        {/* Market Snapshot */}
        <Text style={styles.sectionTitle}>Market Snapshot</Text>
        <View style={styles.marketGrid}>
          <View style={styles.marketCard}>
            <View style={styles.marketHeader}>
              <Ionicons name="logo-bitcoin" size={20} color="#f7931a" />
              <Text style={styles.marketSymbol}>BTC</Text>
            </View>
            <Text style={styles.marketPrice}>{formatCurrency(marketSnapshot?.btc_price || 0)}</Text>
            <View style={styles.marketStats}>
              <Text style={[
                styles.marketChange,
                { color: (marketSnapshot?.btc_change || 0) >= 0 ? '#10b981' : '#ef4444' }
              ]}>
                {(marketSnapshot?.btc_change || 0) >= 0 ? '+' : ''}{marketSnapshot?.btc_change?.toFixed(1)}%
              </Text>
              <Text style={styles.marketRsi}>RSI: {marketSnapshot?.btc_rsi}</Text>
            </View>
          </View>

          <View style={styles.marketCard}>
            <View style={styles.marketHeader}>
              <Ionicons name="diamond" size={20} color="#627eea" />
              <Text style={styles.marketSymbol}>ETH</Text>
            </View>
            <Text style={styles.marketPrice}>{formatCurrency(marketSnapshot?.eth_price || 0)}</Text>
            <View style={styles.marketStats}>
              <Text style={[
                styles.marketChange,
                { color: (marketSnapshot?.eth_change || 0) >= 0 ? '#10b981' : '#ef4444' }
              ]}>
                {(marketSnapshot?.eth_change || 0) >= 0 ? '+' : ''}{marketSnapshot?.eth_change?.toFixed(1)}%
              </Text>
              <Text style={styles.marketRsi}>RSI: {marketSnapshot?.eth_rsi}</Text>
            </View>
          </View>

          <View style={styles.marketCard}>
            <View style={styles.marketHeader}>
              <Ionicons name="trending-up" size={20} color="#3b82f6" />
              <Text style={styles.marketSymbol}>NIFTY</Text>
            </View>
            <Text style={styles.marketPrice}>{marketSnapshot?.nifty_level?.toLocaleString('en-IN')}</Text>
            <View style={styles.marketStats}>
              <Text style={[
                styles.marketChange,
                { color: (marketSnapshot?.nifty_change || 0) >= 0 ? '#10b981' : '#ef4444' }
              ]}>
                {(marketSnapshot?.nifty_change || 0) >= 0 ? '+' : ''}{marketSnapshot?.nifty_change?.toFixed(1)}%
              </Text>
            </View>
          </View>

          <View style={styles.marketCard}>
            <View style={styles.marketHeader}>
              <Ionicons name="cash" size={20} color="#f59e0b" />
              <Text style={styles.marketSymbol}>INR/USD</Text>
            </View>
            <Text style={styles.marketPrice}>{marketSnapshot?.inr_usd?.toFixed(2)}</Text>
          </View>
        </View>

        {/* Allocations */}
        {decision?.recommendation !== 'Hold' && (
          <>
            <Text style={styles.sectionTitle}>Suggested Allocations</Text>
            <View style={styles.allocationContainer}>
              {decision?.allocations?.crypto && Object.keys(decision.allocations.crypto).length > 0 && (
                <View style={styles.allocationSection}>
                  <Text style={styles.allocationTitle}>
                    <Ionicons name="logo-bitcoin" size={16} color="#10b981" /> Crypto
                  </Text>
                  {Object.entries(decision.allocations.crypto).map(([symbol, pct]) => (
                    <View key={symbol} style={styles.allocationItem}>
                      <Text style={styles.allocationSymbol}>{symbol}</Text>
                      <View style={styles.allocationBarContainer}>
                        <View style={[styles.allocationBar, { width: `${pct}%`, backgroundColor: '#10b981' }]} />
                      </View>
                      <Text style={styles.allocationPct}>{pct}%</Text>
                    </View>
                  ))}
                </View>
              )}
              {decision?.allocations?.stocks && Object.keys(decision.allocations.stocks).length > 0 && (
                <View style={styles.allocationSection}>
                  <Text style={styles.allocationTitle}>
                    <Ionicons name="business" size={16} color="#3b82f6" /> Stocks
                  </Text>
                  {Object.entries(decision.allocations.stocks).map(([symbol, pct]) => (
                    <View key={symbol} style={styles.allocationItem}>
                      <Text style={styles.allocationSymbol}>{symbol}</Text>
                      <View style={styles.allocationBarContainer}>
                        <View style={[styles.allocationBar, { width: `${pct}%`, backgroundColor: '#3b82f6' }]} />
                      </View>
                      <Text style={styles.allocationPct}>{pct}%</Text>
                    </View>
                  ))}
                </View>
              )}
            </View>
          </>
        )}

        {/* Reasoning */}
        <Text style={styles.sectionTitle}>Analysis & Reasoning</Text>
        <View style={styles.reasoningCard}>
          <Text style={styles.reasoningText}>{decision?.reasoning}</Text>
        </View>

        {/* Risks */}
        <Text style={styles.sectionTitle}>Key Risks</Text>
        <View style={styles.risksContainer}>
          {decision?.risks?.map((risk, index) => (
            <View key={index} style={styles.riskItem}>
              <Ionicons name="warning" size={16} color="#f59e0b" />
              <Text style={styles.riskText}>{risk}</Text>
            </View>
          ))}
        </View>

        {/* Timeline */}
        <View style={styles.timelineCard}>
          <Ionicons name="time" size={20} color="#8b5cf6" />
          <View style={styles.timelineContent}>
            <Text style={styles.timelineLabel}>Suggested Timeline</Text>
            <Text style={styles.timelineValue}>{decision?.timeline}</Text>
          </View>
        </View>

        {/* Disclaimer */}
        <View style={styles.disclaimerCard}>
          <Ionicons name="information-circle" size={20} color="#6b7280" />
          <Text style={styles.disclaimerText}>
            This is AI-generated analysis for educational purposes only. Not financial advice. Always DYOR.
          </Text>
        </View>
      </ScrollView>
    </SafeAreaView>
  );
}

const styles = StyleSheet.create({
  container: {
    flex: 1,
    backgroundColor: '#0f0f23',
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
  scrollView: {
    flex: 1,
  },
  content: {
    padding: 20,
  },
  header: {
    marginBottom: 20,
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
  recommendationCard: {
    backgroundColor: '#1a1a2e',
    borderRadius: 16,
    padding: 20,
    borderWidth: 2,
    marginBottom: 24,
  },
  recommendationHeader: {
    flexDirection: 'row',
    alignItems: 'center',
    marginBottom: 20,
  },
  recommendationIcon: {
    width: 64,
    height: 64,
    borderRadius: 16,
    justifyContent: 'center',
    alignItems: 'center',
  },
  recommendationInfo: {
    marginLeft: 16,
  },
  recommendationLabel: {
    fontSize: 12,
    color: '#9ca3af',
    fontWeight: '600',
    letterSpacing: 1,
  },
  recommendationValue: {
    fontSize: 28,
    fontWeight: '700',
    marginTop: 4,
  },
  confidenceBar: {
    marginTop: 8,
  },
  confidenceLabel: {
    flexDirection: 'row',
    justifyContent: 'space-between',
    marginBottom: 8,
  },
  confidenceText: {
    color: '#9ca3af',
    fontSize: 14,
  },
  confidenceValue: {
    color: '#fff',
    fontSize: 14,
    fontWeight: '600',
  },
  confidenceTrack: {
    height: 8,
    backgroundColor: '#2d2d44',
    borderRadius: 4,
    overflow: 'hidden',
  },
  confidenceFill: {
    height: '100%',
    borderRadius: 4,
  },
  sectionTitle: {
    fontSize: 18,
    fontWeight: '600',
    color: '#fff',
    marginBottom: 12,
  },
  marketGrid: {
    flexDirection: 'row',
    flexWrap: 'wrap',
    justifyContent: 'space-between',
    marginBottom: 24,
  },
  marketCard: {
    width: '48%',
    backgroundColor: '#1a1a2e',
    borderRadius: 12,
    padding: 16,
    marginBottom: 12,
  },
  marketHeader: {
    flexDirection: 'row',
    alignItems: 'center',
    marginBottom: 8,
  },
  marketSymbol: {
    color: '#fff',
    fontWeight: '600',
    marginLeft: 8,
  },
  marketPrice: {
    color: '#fff',
    fontSize: 18,
    fontWeight: '700',
  },
  marketStats: {
    flexDirection: 'row',
    justifyContent: 'space-between',
    marginTop: 8,
  },
  marketChange: {
    fontSize: 14,
    fontWeight: '500',
  },
  marketRsi: {
    fontSize: 12,
    color: '#6b7280',
  },
  allocationContainer: {
    backgroundColor: '#1a1a2e',
    borderRadius: 16,
    padding: 16,
    marginBottom: 24,
  },
  allocationSection: {
    marginBottom: 16,
  },
  allocationTitle: {
    color: '#fff',
    fontWeight: '600',
    marginBottom: 12,
  },
  allocationItem: {
    flexDirection: 'row',
    alignItems: 'center',
    marginBottom: 8,
  },
  allocationSymbol: {
    color: '#9ca3af',
    width: 80,
    fontSize: 14,
  },
  allocationBarContainer: {
    flex: 1,
    height: 8,
    backgroundColor: '#2d2d44',
    borderRadius: 4,
    marginHorizontal: 12,
  },
  allocationBar: {
    height: '100%',
    borderRadius: 4,
  },
  allocationPct: {
    color: '#fff',
    fontSize: 14,
    fontWeight: '500',
    width: 40,
    textAlign: 'right',
  },
  reasoningCard: {
    backgroundColor: '#1a1a2e',
    borderRadius: 16,
    padding: 16,
    marginBottom: 24,
  },
  reasoningText: {
    color: '#d1d5db',
    fontSize: 14,
    lineHeight: 22,
  },
  risksContainer: {
    backgroundColor: '#1a1a2e',
    borderRadius: 16,
    padding: 16,
    marginBottom: 24,
  },
  riskItem: {
    flexDirection: 'row',
    alignItems: 'flex-start',
    marginBottom: 12,
  },
  riskText: {
    color: '#d1d5db',
    fontSize: 14,
    marginLeft: 12,
    flex: 1,
  },
  timelineCard: {
    flexDirection: 'row',
    alignItems: 'center',
    backgroundColor: '#1a1a2e',
    borderRadius: 16,
    padding: 16,
    marginBottom: 24,
  },
  timelineContent: {
    marginLeft: 12,
  },
  timelineLabel: {
    fontSize: 12,
    color: '#9ca3af',
  },
  timelineValue: {
    fontSize: 16,
    color: '#fff',
    fontWeight: '600',
    marginTop: 4,
  },
  disclaimerCard: {
    flexDirection: 'row',
    alignItems: 'flex-start',
    backgroundColor: 'rgba(107, 114, 128, 0.1)',
    borderRadius: 12,
    padding: 16,
    marginBottom: 20,
  },
  disclaimerText: {
    color: '#6b7280',
    fontSize: 12,
    marginLeft: 12,
    flex: 1,
    lineHeight: 18,
  },
});
