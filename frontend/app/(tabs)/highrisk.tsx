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

interface Opportunity {
  type: string;
  symbol: string;
  name: string;
  price_inr: number;
  change_24h: number;
  volatility_indicator: string;
  upside_estimate_pct: number;
  downside_estimate_pct: number;
  probability_profit: number;
  suggested_allocation_pct: number;
  stop_loss_pct: number;
  expected_catalysts: string[];
}

interface HighRiskData {
  horizon: string;
  hold_time: string;
  crypto_opportunities: Opportunity[];
  stock_opportunities: Opportunity[];
  reasoning: string;
  extreme_risk_warning: string;
}

const HORIZONS = [
  { key: 'day', label: 'Day Trade', icon: 'flash' },
  { key: '4weeks', label: '4 Weeks', icon: 'calendar' },
  { key: '12weeks', label: '12 Weeks', icon: 'calendar-outline' },
  { key: '52weeks', label: '52 Weeks', icon: 'time' },
];

export default function HighRiskScreen() {
  const [selectedHorizon, setSelectedHorizon] = useState('4weeks');
  const [data, setData] = useState<HighRiskData | null>(null);
  const [loading, setLoading] = useState(true);
  const [refreshing, setRefreshing] = useState(false);

  useEffect(() => {
    fetchData();
  }, [selectedHorizon]);

  const fetchData = async () => {
    try {
      setLoading(true);
      const response = await fetch(`${process.env.EXPO_PUBLIC_BACKEND_URL || ''}/api/highrisk/${selectedHorizon}`);
      const result = await response.json();
      setData(result);
    } catch (error) {
      console.error('Error fetching high risk data:', error);
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

  const renderOpportunityCard = (opp: Opportunity, index: number) => (
    <View key={`${opp.type}_${opp.symbol}`} style={styles.oppCard}>
      <View style={styles.oppHeader}>
        <View style={styles.oppInfo}>
          <View style={[
            styles.typeBadge,
            { backgroundColor: opp.type === 'crypto' ? '#f7931a20' : '#3b82f620' }
          ]}>
            <Ionicons 
              name={opp.type === 'crypto' ? 'logo-bitcoin' : 'business'} 
              size={16} 
              color={opp.type === 'crypto' ? '#f7931a' : '#3b82f6'} 
            />
          </View>
          <View>
            <Text style={styles.oppSymbol}>{opp.symbol}</Text>
            <Text style={styles.oppName} numberOfLines={1}>{opp.name}</Text>
          </View>
        </View>
        <View style={styles.oppPriceContainer}>
          <Text style={styles.oppPrice}>{formatCurrency(opp.price_inr)}</Text>
          <View style={[
            styles.volatilityBadge,
            { backgroundColor: opp.volatility_indicator === 'EXTREME' ? '#ef444420' : '#f59e0b20' }
          ]}>
            <Text style={[
              styles.volatilityText,
              { color: opp.volatility_indicator === 'EXTREME' ? '#ef4444' : '#f59e0b' }
            ]}>
              {opp.volatility_indicator}
            </Text>
          </View>
        </View>
      </View>

      <View style={styles.estimatesContainer}>
        <View style={styles.estimateItem}>
          <Text style={styles.estimateLabel}>Upside</Text>
          <Text style={[styles.estimateValue, { color: '#10b981' }]}>+{opp.upside_estimate_pct}%</Text>
        </View>
        <View style={styles.estimateItem}>
          <Text style={styles.estimateLabel}>Downside</Text>
          <Text style={[styles.estimateValue, { color: '#ef4444' }]}>-{opp.downside_estimate_pct}%</Text>
        </View>
        <View style={styles.estimateItem}>
          <Text style={styles.estimateLabel}>Win Prob</Text>
          <Text style={styles.estimateValue}>{opp.probability_profit}%</Text>
        </View>
      </View>

      <View style={styles.oppDetails}>
        <View style={styles.detailRow}>
          <Text style={styles.detailLabel}>Max Allocation</Text>
          <Text style={styles.detailValue}>{opp.suggested_allocation_pct}% of capital</Text>
        </View>
        <View style={styles.detailRow}>
          <Text style={styles.detailLabel}>Stop Loss</Text>
          <Text style={[styles.detailValue, { color: '#ef4444' }]}>{opp.stop_loss_pct}%</Text>
        </View>
      </View>

      <View style={styles.catalystsContainer}>
        <Text style={styles.catalystsLabel}>Expected Catalysts:</Text>
        {opp.expected_catalysts.map((catalyst, i) => (
          <View key={i} style={styles.catalystItem}>
            <Ionicons name="arrow-forward" size={12} color="#6b7280" />
            <Text style={styles.catalystText}>{catalyst}</Text>
          </View>
        ))}
      </View>
    </View>
  );

  return (
    <SafeAreaView style={styles.container} edges={['top']}>
      {/* Extreme Risk Banner */}
      <View style={styles.riskBanner}>
        <Ionicons name="skull" size={24} color="#ef4444" />
        <Text style={styles.riskBannerText}>
          EXTREME RISK - 50-100% loss probability HIGH. Educational/virtual only.
        </Text>
      </View>

      <ScrollView
        style={styles.scrollView}
        contentContainerStyle={styles.content}
        refreshControl={
          <RefreshControl refreshing={refreshing} onRefresh={onRefresh} tintColor="#ef4444" />
        }
      >
        <View style={styles.header}>
          <Text style={styles.headerTitle}>High Risk</Text>
          <Text style={styles.headerSubtitle}>High Volatility Opportunities</Text>
        </View>

        {/* Horizon Selector */}
        <ScrollView 
          horizontal 
          showsHorizontalScrollIndicator={false}
          style={styles.horizonScroll}
          contentContainerStyle={styles.horizonContainer}
        >
          {HORIZONS.map((h) => (
            <TouchableOpacity
              key={h.key}
              style={[styles.horizonButton, selectedHorizon === h.key && styles.horizonButtonActive]}
              onPress={() => setSelectedHorizon(h.key)}
            >
              <Ionicons 
                name={h.icon as any} 
                size={16} 
                color={selectedHorizon === h.key ? '#fff' : '#9ca3af'} 
              />
              <Text style={[styles.horizonText, selectedHorizon === h.key && styles.horizonTextActive]}>
                {h.label}
              </Text>
            </TouchableOpacity>
          ))}
        </ScrollView>

        {loading ? (
          <View style={styles.loadingContainer}>
            <ActivityIndicator size="large" color="#ef4444" />
            <Text style={styles.loadingText}>Finding opportunities...</Text>
          </View>
        ) : (
          <>
            {/* Hold Time Badge */}
            <View style={styles.holdTimeBadge}>
              <Ionicons name="time" size={16} color="#8b5cf6" />
              <Text style={styles.holdTimeText}>Hold Time: {data?.hold_time}</Text>
            </View>

            {/* Crypto Opportunities */}
            {data?.crypto_opportunities && data.crypto_opportunities.length > 0 && (
              <>
                <Text style={styles.sectionTitle}>
                  <Ionicons name="logo-bitcoin" size={18} color="#f7931a" /> Crypto Opportunities
                </Text>
                {data.crypto_opportunities.map((opp, i) => renderOpportunityCard(opp, i))}
              </>
            )}

            {/* Stock Opportunities */}
            {data?.stock_opportunities && data.stock_opportunities.length > 0 && (
              <>
                <Text style={styles.sectionTitle}>
                  <Ionicons name="trending-up" size={18} color="#3b82f6" /> Stock Opportunities
                </Text>
                {data.stock_opportunities.map((opp, i) => renderOpportunityCard(opp, i))}
              </>
            )}

            {/* No Opportunities */}
            {(!data?.crypto_opportunities?.length && !data?.stock_opportunities?.length) && (
              <View style={styles.emptyState}>
                <Ionicons name="search" size={48} color="#6b7280" />
                <Text style={styles.emptyText}>No high-risk opportunities found</Text>
                <Text style={styles.emptySubtext}>Market conditions may be unfavorable</Text>
              </View>
            )}

            {/* Reasoning */}
            <Text style={styles.sectionTitle}>AI Analysis</Text>
            <View style={styles.reasoningCard}>
              <Text style={styles.reasoningText}>{data?.reasoning}</Text>
            </View>

            {/* Final Warning */}
            <View style={styles.finalWarning}>
              <Ionicons name="warning" size={24} color="#ef4444" />
              <View style={styles.warningContent}>
                <Text style={styles.warningTitle}>FINAL WARNING</Text>
                <Text style={styles.warningText}>
                  {data?.extreme_risk_warning}
                </Text>
                <Text style={styles.warningNote}>
                  30% VDA tax in India means you need 43% gains just to break even after tax on crypto.
                </Text>
              </View>
            </View>
          </>
        )}
      </ScrollView>
    </SafeAreaView>
  );
}

const styles = StyleSheet.create({
  container: {
    flex: 1,
    backgroundColor: '#0f0f23',
  },
  riskBanner: {
    flexDirection: 'row',
    alignItems: 'center',
    backgroundColor: 'rgba(239, 68, 68, 0.2)',
    padding: 12,
    borderBottomWidth: 1,
    borderBottomColor: '#ef4444',
  },
  riskBannerText: {
    color: '#ef4444',
    fontSize: 12,
    fontWeight: '700',
    marginLeft: 8,
    flex: 1,
  },
  scrollView: {
    flex: 1,
  },
  content: {
    padding: 20,
  },
  header: {
    marginBottom: 16,
  },
  headerTitle: {
    fontSize: 28,
    fontWeight: '700',
    color: '#ef4444',
  },
  headerSubtitle: {
    fontSize: 14,
    color: '#9ca3af',
    marginTop: 4,
  },
  horizonScroll: {
    marginBottom: 16,
  },
  horizonContainer: {
    gap: 8,
  },
  horizonButton: {
    flexDirection: 'row',
    alignItems: 'center',
    backgroundColor: '#1a1a2e',
    paddingVertical: 10,
    paddingHorizontal: 16,
    borderRadius: 20,
    marginRight: 8,
  },
  horizonButtonActive: {
    backgroundColor: '#ef4444',
  },
  horizonText: {
    color: '#9ca3af',
    marginLeft: 6,
    fontWeight: '500',
  },
  horizonTextActive: {
    color: '#fff',
  },
  loadingContainer: {
    paddingVertical: 60,
    alignItems: 'center',
  },
  loadingText: {
    color: '#9ca3af',
    marginTop: 12,
  },
  holdTimeBadge: {
    flexDirection: 'row',
    alignItems: 'center',
    alignSelf: 'flex-start',
    backgroundColor: '#8b5cf620',
    paddingVertical: 6,
    paddingHorizontal: 12,
    borderRadius: 16,
    marginBottom: 20,
  },
  holdTimeText: {
    color: '#8b5cf6',
    marginLeft: 6,
    fontWeight: '600',
  },
  sectionTitle: {
    fontSize: 18,
    fontWeight: '600',
    color: '#fff',
    marginBottom: 12,
    marginTop: 8,
  },
  oppCard: {
    backgroundColor: '#1a1a2e',
    borderRadius: 12,
    padding: 16,
    marginBottom: 12,
    borderWidth: 1,
    borderColor: '#ef444440',
  },
  oppHeader: {
    flexDirection: 'row',
    justifyContent: 'space-between',
    alignItems: 'flex-start',
  },
  oppInfo: {
    flexDirection: 'row',
    alignItems: 'center',
  },
  typeBadge: {
    width: 32,
    height: 32,
    borderRadius: 8,
    justifyContent: 'center',
    alignItems: 'center',
    marginRight: 12,
  },
  oppSymbol: {
    color: '#fff',
    fontSize: 16,
    fontWeight: '600',
  },
  oppName: {
    color: '#6b7280',
    fontSize: 12,
    maxWidth: 120,
  },
  oppPriceContainer: {
    alignItems: 'flex-end',
  },
  oppPrice: {
    color: '#fff',
    fontSize: 16,
    fontWeight: '600',
  },
  volatilityBadge: {
    paddingHorizontal: 8,
    paddingVertical: 2,
    borderRadius: 4,
    marginTop: 4,
  },
  volatilityText: {
    fontSize: 10,
    fontWeight: '700',
  },
  estimatesContainer: {
    flexDirection: 'row',
    justifyContent: 'space-around',
    marginTop: 16,
    paddingTop: 16,
    borderTopWidth: 1,
    borderTopColor: '#2d2d44',
  },
  estimateItem: {
    alignItems: 'center',
  },
  estimateLabel: {
    color: '#6b7280',
    fontSize: 11,
  },
  estimateValue: {
    color: '#fff',
    fontSize: 18,
    fontWeight: '700',
    marginTop: 4,
  },
  oppDetails: {
    marginTop: 16,
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
  catalystsContainer: {
    marginTop: 12,
    paddingTop: 12,
    borderTopWidth: 1,
    borderTopColor: '#2d2d44',
  },
  catalystsLabel: {
    color: '#9ca3af',
    fontSize: 12,
    marginBottom: 8,
  },
  catalystItem: {
    flexDirection: 'row',
    alignItems: 'center',
    marginBottom: 4,
  },
  catalystText: {
    color: '#d1d5db',
    fontSize: 12,
    marginLeft: 8,
  },
  emptyState: {
    alignItems: 'center',
    paddingVertical: 40,
  },
  emptyText: {
    color: '#fff',
    fontSize: 16,
    marginTop: 12,
  },
  emptySubtext: {
    color: '#6b7280',
    fontSize: 14,
    marginTop: 4,
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
  finalWarning: {
    flexDirection: 'row',
    backgroundColor: 'rgba(239, 68, 68, 0.15)',
    borderRadius: 12,
    padding: 16,
    marginBottom: 20,
    borderWidth: 1,
    borderColor: '#ef4444',
  },
  warningContent: {
    flex: 1,
    marginLeft: 12,
  },
  warningTitle: {
    color: '#ef4444',
    fontSize: 14,
    fontWeight: '700',
    marginBottom: 8,
  },
  warningText: {
    color: '#ef4444',
    fontSize: 12,
    lineHeight: 18,
    marginBottom: 8,
  },
  warningNote: {
    color: '#f59e0b',
    fontSize: 11,
    fontStyle: 'italic',
  },
});
