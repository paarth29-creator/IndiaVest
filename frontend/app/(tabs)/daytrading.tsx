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

interface Recommendation {
  symbol: string;
  name: string;
  current_price_inr: number;
  change_24h: number;
  entry_range: { low: number; high: number };
  stop_loss: number;
  stop_loss_pct: number;
  take_profit: { tp1_1to1: number; tp2_1to2: number; tp3_1to3: number };
  max_position_pct: number;
  signal_strength: string;
}

interface DayTradingData {
  should_trade: boolean;
  confidence: number;
  score: number;
  market_conditions: {
    total_volume_usd: number;
    avg_volatility: number;
    liquid_coins_count: number;
    is_good_hours: boolean;
    ist_time: string;
  };
  top_5_recommendations: Recommendation[];
  reasoning: string;
  extreme_risk_warning: string;
}

export default function DayTradingScreen() {
  const [data, setData] = useState<DayTradingData | null>(null);
  const [loading, setLoading] = useState(true);
  const [refreshing, setRefreshing] = useState(false);
  const [selectedCoin, setSelectedCoin] = useState<string | null>(null);

  useEffect(() => {
    fetchData();
  }, []);

  const fetchData = async () => {
    try {
      setLoading(true);
      const response: any = await fetch(`${process.env.EXPO_PUBLIC_BACKEND_URL || ''}/api/daytrading/should-trade`);
      const result = await response.json();
      setData(result);
    } catch (error) {
      console.error('Error fetching day trading data:', error);
    } finally {
      setLoading(false);
    }
  };

  const onRefresh = async () => {
    setRefreshing(true);
    await fetchData();
    setRefreshing(false);
  };

  const formatCurrency = (value: number) => {
    if (value >= 100000) {
      return `₹${(value / 100000).toFixed(2)}L`;
    }
    return `₹${value.toLocaleString('en-IN', { maximumFractionDigits: 2 })}`;
  };

  const formatVolume = (value: number) => {
    if (value >= 1e9) return `$${(value / 1e9).toFixed(1)}B`;
    if (value >= 1e6) return `$${(value / 1e6).toFixed(1)}M`;
    return `$${value.toFixed(0)}`;
  };

  if (loading) {
    return (
      <SafeAreaView style={styles.container} edges={['top']}>
        <View style={styles.loadingContainer}>
          <ActivityIndicator size="large" color="#f59e0b" />
          <Text style={styles.loadingText}>Analyzing markets...</Text>
        </View>
      </SafeAreaView>
    );
  }

  const signalColor = data?.should_trade ? '#10b981' : '#ef4444';

  return (
    <SafeAreaView style={styles.container} edges={['top']}>
      <ScrollView
        style={styles.scrollView}
        contentContainerStyle={styles.content}
        refreshControl={
          <RefreshControl refreshing={refreshing} onRefresh={onRefresh} tintColor="#f59e0b" />
        }
      >
        {/* Warning Banner */}
        <View style={styles.warningBanner}>
          <Ionicons name="warning" size={20} color="#f59e0b" />
          <Text style={styles.warningText}>
            EXTREME RISK: 90%+ day traders lose money. Educational/virtual use only.
          </Text>
        </View>

        <View style={styles.header}>
          <Text style={styles.headerTitle}>Day Trading</Text>
          <Text style={styles.headerSubtitle}>Crypto Intraday Analysis</Text>
        </View>

        {/* Main Decision Card */}
        <View style={[styles.decisionCard, { borderColor: signalColor }]}>
          <Text style={styles.decisionQuestion}>Should I Day Trade Crypto Today?</Text>
          
          <View style={styles.decisionResult}>
            <View style={[styles.decisionBadge, { backgroundColor: signalColor + '20' }]}>
              <Ionicons 
                name={data?.should_trade ? 'checkmark-circle' : 'close-circle'} 
                size={48} 
                color={signalColor} 
              />
            </View>
            <Text style={[styles.decisionText, { color: signalColor }]}>
              {data?.should_trade ? 'YES' : 'NO'}
            </Text>
          </View>

          <View style={styles.confidenceContainer}>
            <View style={styles.confidenceHeader}>
              <Text style={styles.confidenceLabel}>Confidence</Text>
              <Text style={styles.confidenceValue}>{data?.confidence?.toFixed(0)}%</Text>
            </View>
            <View style={styles.confidenceBar}>
              <View 
                style={[
                  styles.confidenceFill, 
                  { width: `${data?.confidence || 0}%`, backgroundColor: signalColor }
                ]} 
              />
            </View>
          </View>

          <View style={styles.scoreContainer}>
            <Text style={styles.scoreText}>Market Score: {data?.score?.toFixed(0)}/90</Text>
          </View>
        </View>

        {/* Market Conditions */}
        <Text style={styles.sectionTitle}>Market Conditions</Text>
        <View style={styles.conditionsGrid}>
          <View style={styles.conditionCard}>
            <Ionicons name="bar-chart" size={24} color="#3b82f6" />
            <Text style={styles.conditionValue}>{formatVolume(data?.market_conditions?.total_volume_usd || 0)}</Text>
            <Text style={styles.conditionLabel}>24h Volume</Text>
          </View>
          <View style={styles.conditionCard}>
            <Ionicons name="pulse" size={24} color="#f59e0b" />
            <Text style={styles.conditionValue}>{data?.market_conditions?.avg_volatility?.toFixed(1)}%</Text>
            <Text style={styles.conditionLabel}>Avg Volatility</Text>
          </View>
          <View style={styles.conditionCard}>
            <Ionicons name="water" size={24} color="#10b981" />
            <Text style={styles.conditionValue}>{data?.market_conditions?.liquid_coins_count}</Text>
            <Text style={styles.conditionLabel}>Liquid Coins</Text>
          </View>
          <View style={styles.conditionCard}>
            <Ionicons name="time" size={24} color={data?.market_conditions?.is_good_hours ? '#10b981' : '#ef4444'} />
            <Text style={styles.conditionValue}>{data?.market_conditions?.ist_time}</Text>
            <Text style={styles.conditionLabel}>{data?.market_conditions?.is_good_hours ? 'Active' : 'Off-peak'}</Text>
          </View>
        </View>

        {/* Top 5 Recommendations */}
        <Text style={styles.sectionTitle}>Top 5 Trading Opportunities</Text>
        {data?.top_5_recommendations?.map((coin, index) => (
          <TouchableOpacity
            key={coin.symbol}
            style={styles.coinCard}
            onPress={() => setSelectedCoin(selectedCoin === coin.symbol ? null : coin.symbol)}
          >
            <View style={styles.coinHeader}>
              <View style={styles.coinInfo}>
                <View style={styles.coinRank}>
                  <Text style={styles.rankText}>#{index + 1}</Text>
                </View>
                <View>
                  <Text style={styles.coinSymbol}>{coin.symbol}</Text>
                  <Text style={styles.coinName}>{coin.name}</Text>
                </View>
              </View>
              <View style={styles.coinPriceContainer}>
                <Text style={styles.coinPrice}>{formatCurrency(coin.current_price_inr)}</Text>
                <View style={[
                  styles.signalBadge,
                  { backgroundColor: coin.signal_strength === 'strong' ? '#10b98120' : coin.signal_strength === 'moderate' ? '#f59e0b20' : '#6b728020' }
                ]}>
                  <Text style={[
                    styles.signalText,
                    { color: coin.signal_strength === 'strong' ? '#10b981' : coin.signal_strength === 'moderate' ? '#f59e0b' : '#6b7280' }
                  ]}>
                    {coin.signal_strength.toUpperCase()}
                  </Text>
                </View>
              </View>
            </View>

            {selectedCoin === coin.symbol && (
              <View style={styles.coinDetails}>
                <View style={styles.detailRow}>
                  <Text style={styles.detailLabel}>Entry Range</Text>
                  <Text style={styles.detailValue}>
                    {formatCurrency(coin.entry_range.low)} - {formatCurrency(coin.entry_range.high)}
                  </Text>
                </View>
                <View style={styles.detailRow}>
                  <Text style={styles.detailLabel}>Stop Loss</Text>
                  <Text style={[styles.detailValue, { color: '#ef4444' }]}>
                    {formatCurrency(coin.stop_loss)} (-{coin.stop_loss_pct}%)
                  </Text>
                </View>
                <View style={styles.detailRow}>
                  <Text style={styles.detailLabel}>Take Profit (1:1)</Text>
                  <Text style={[styles.detailValue, { color: '#10b981' }]}>
                    {formatCurrency(coin.take_profit.tp1_1to1)}
                  </Text>
                </View>
                <View style={styles.detailRow}>
                  <Text style={styles.detailLabel}>Take Profit (1:2)</Text>
                  <Text style={[styles.detailValue, { color: '#10b981' }]}>
                    {formatCurrency(coin.take_profit.tp2_1to2)}
                  </Text>
                </View>
                <View style={styles.detailRow}>
                  <Text style={styles.detailLabel}>Max Position</Text>
                  <Text style={styles.detailValue}>{coin.max_position_pct}% of capital</Text>
                </View>
                <View style={styles.detailRow}>
                  <Text style={styles.detailLabel}>Expected Hold</Text>
                  <Text style={styles.detailValue}>&lt;4 hours</Text>
                </View>
              </View>
            )}

            <View style={styles.expandIcon}>
              <Ionicons 
                name={selectedCoin === coin.symbol ? 'chevron-up' : 'chevron-down'} 
                size={20} 
                color="#6b7280" 
              />
            </View>
          </TouchableOpacity>
        ))}

        {/* Reasoning */}
        <Text style={styles.sectionTitle}>AI Analysis</Text>
        <View style={styles.reasoningCard}>
          <Text style={styles.reasoningText}>{data?.reasoning}</Text>
        </View>

        {/* Disclaimer */}
        <View style={styles.disclaimerCard}>
          <Ionicons name="alert-circle" size={20} color="#ef4444" />
          <Text style={styles.disclaimerText}>
            This is NOT financial advice. 30% VDA tax applies to all crypto gains in India. 
            Virtual/educational use only. Never invest money you cannot afford to lose.
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
  warningBanner: {
    flexDirection: 'row',
    alignItems: 'center',
    backgroundColor: 'rgba(245, 158, 11, 0.15)',
    padding: 12,
    borderRadius: 12,
    marginBottom: 16,
  },
  warningText: {
    color: '#f59e0b',
    fontSize: 12,
    fontWeight: '600',
    marginLeft: 8,
    flex: 1,
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
  decisionCard: {
    backgroundColor: '#1a1a2e',
    borderRadius: 16,
    padding: 24,
    borderWidth: 2,
    marginBottom: 24,
    alignItems: 'center',
  },
  decisionQuestion: {
    fontSize: 18,
    fontWeight: '600',
    color: '#fff',
    marginBottom: 20,
    textAlign: 'center',
  },
  decisionResult: {
    alignItems: 'center',
    marginBottom: 20,
  },
  decisionBadge: {
    width: 80,
    height: 80,
    borderRadius: 40,
    justifyContent: 'center',
    alignItems: 'center',
    marginBottom: 12,
  },
  decisionText: {
    fontSize: 36,
    fontWeight: '700',
  },
  confidenceContainer: {
    width: '100%',
    marginBottom: 16,
  },
  confidenceHeader: {
    flexDirection: 'row',
    justifyContent: 'space-between',
    marginBottom: 8,
  },
  confidenceLabel: {
    color: '#9ca3af',
    fontSize: 14,
  },
  confidenceValue: {
    color: '#fff',
    fontSize: 14,
    fontWeight: '600',
  },
  confidenceBar: {
    height: 8,
    backgroundColor: '#2d2d44',
    borderRadius: 4,
    overflow: 'hidden',
  },
  confidenceFill: {
    height: '100%',
    borderRadius: 4,
  },
  scoreContainer: {
    backgroundColor: '#0f0f23',
    paddingHorizontal: 16,
    paddingVertical: 8,
    borderRadius: 20,
  },
  scoreText: {
    color: '#9ca3af',
    fontSize: 14,
    fontWeight: '500',
  },
  sectionTitle: {
    fontSize: 18,
    fontWeight: '600',
    color: '#fff',
    marginBottom: 12,
  },
  conditionsGrid: {
    flexDirection: 'row',
    flexWrap: 'wrap',
    justifyContent: 'space-between',
    marginBottom: 24,
  },
  conditionCard: {
    width: '48%',
    backgroundColor: '#1a1a2e',
    borderRadius: 12,
    padding: 16,
    alignItems: 'center',
    marginBottom: 12,
  },
  conditionValue: {
    color: '#fff',
    fontSize: 18,
    fontWeight: '700',
    marginTop: 8,
  },
  conditionLabel: {
    color: '#6b7280',
    fontSize: 12,
    marginTop: 4,
  },
  coinCard: {
    backgroundColor: '#1a1a2e',
    borderRadius: 12,
    padding: 16,
    marginBottom: 12,
  },
  coinHeader: {
    flexDirection: 'row',
    justifyContent: 'space-between',
    alignItems: 'center',
  },
  coinInfo: {
    flexDirection: 'row',
    alignItems: 'center',
  },
  coinRank: {
    width: 28,
    height: 28,
    borderRadius: 14,
    backgroundColor: '#f59e0b20',
    justifyContent: 'center',
    alignItems: 'center',
    marginRight: 12,
  },
  rankText: {
    color: '#f59e0b',
    fontSize: 12,
    fontWeight: '700',
  },
  coinSymbol: {
    color: '#fff',
    fontSize: 16,
    fontWeight: '600',
  },
  coinName: {
    color: '#6b7280',
    fontSize: 12,
  },
  coinPriceContainer: {
    alignItems: 'flex-end',
  },
  coinPrice: {
    color: '#fff',
    fontSize: 16,
    fontWeight: '600',
  },
  signalBadge: {
    paddingHorizontal: 8,
    paddingVertical: 2,
    borderRadius: 4,
    marginTop: 4,
  },
  signalText: {
    fontSize: 10,
    fontWeight: '700',
  },
  coinDetails: {
    marginTop: 16,
    paddingTop: 16,
    borderTopWidth: 1,
    borderTopColor: '#2d2d44',
  },
  detailRow: {
    flexDirection: 'row',
    justifyContent: 'space-between',
    marginBottom: 8,
  },
  detailLabel: {
    color: '#6b7280',
    fontSize: 13,
  },
  detailValue: {
    color: '#fff',
    fontSize: 13,
    fontWeight: '500',
  },
  expandIcon: {
    alignItems: 'center',
    marginTop: 8,
  },
  reasoningCard: {
    backgroundColor: '#1a1a2e',
    borderRadius: 12,
    padding: 16,
    marginBottom: 24,
  },
  reasoningText: {
    color: '#d1d5db',
    fontSize: 14,
    lineHeight: 22,
  },
  disclaimerCard: {
    flexDirection: 'row',
    alignItems: 'flex-start',
    backgroundColor: 'rgba(239, 68, 68, 0.1)',
    borderRadius: 12,
    padding: 16,
    marginBottom: 20,
  },
  disclaimerText: {
    color: '#ef4444',
    fontSize: 12,
    marginLeft: 12,
    flex: 1,
    lineHeight: 18,
  },
});
