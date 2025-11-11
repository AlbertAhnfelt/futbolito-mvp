import React, { useState } from 'react';
import { Modal, Input, List, Button, Typography, Space, Tag, DatePicker, message } from 'antd';
import { SearchOutlined, TrophyOutlined, CalendarOutlined } from '@ant-design/icons';
import dayjs, { Dayjs } from 'dayjs';
import { footballApi } from '../services/api';
import type { GameSearchResult, GameDetails, GameFilters } from '../types/football';

const { Text } = Typography;
const { RangePicker } = DatePicker;

interface GameSearchModalProps {
  open: boolean;
  onClose: () => void;
  onSelectGame: (game: GameDetails) => void;
}

export const GameSearchModal: React.FC<GameSearchModalProps> = ({
  open,
  onClose,
  onSelectGame,
}) => {
  const [teamQuery, setTeamQuery] = useState('');
  const [dateRange, setDateRange] = useState<[Dayjs | null, Dayjs | null]>([null, null]);
  const [searchResults, setSearchResults] = useState<GameSearchResult[]>([]);
  const [loading, setLoading] = useState(false);
  const [selectedGameId, setSelectedGameId] = useState<string | null>(null);
  const [loadingGameDetails, setLoadingGameDetails] = useState(false);

  const handleSearch = async () => {
    if (!teamQuery && !dateRange[0] && !dateRange[1]) {
      message.warning('Please enter a team name or select a date range');
      return;
    }

    setLoading(true);
    try {
      const filters: GameFilters = {
        team_name: teamQuery || undefined,
        date_from: dateRange[0] ? dateRange[0].format('YYYY-MM-DD') : undefined,
        date_to: dateRange[1] ? dateRange[1].format('YYYY-MM-DD') : undefined,
      };

      const results = await footballApi.searchGames(filters);
      setSearchResults(results);

      if (results.length === 0) {
        message.info('No games found');
      }
    } catch (error) {
      console.error('Error searching games:', error);
      message.error('Failed to search games. Please try again.');
    } finally {
      setLoading(false);
    }
  };

  const handleSelectGame = async (gameId: string) => {
    setLoadingGameDetails(true);
    setSelectedGameId(gameId);

    try {
      const gameDetails = await footballApi.getGame(gameId);
      onSelectGame(gameDetails);
      message.success('Game data loaded successfully');
      handleClose();
    } catch (error) {
      console.error('Error loading game details:', error);
      message.error('Failed to load game details. Please try again.');
    } finally {
      setLoadingGameDetails(false);
      setSelectedGameId(null);
    }
  };

  const handleClose = () => {
    setTeamQuery('');
    setDateRange([null, null]);
    setSearchResults([]);
    setSelectedGameId(null);
    onClose();
  };

  const getStatusColor = (status?: string) => {
    switch (status?.toLowerCase()) {
      case 'finished':
        return 'default';
      case 'live':
        return 'red';
      case 'scheduled':
        return 'blue';
      default:
        return 'default';
    }
  };

  return (
    <Modal
      title="Search Game"
      open={open}
      onCancel={handleClose}
      footer={null}
      width={700}
    >
      <Space direction="vertical" style={{ width: '100%' }} size="large">
        <Space direction="vertical" style={{ width: '100%' }}>
          <Input
            placeholder="Enter team name (optional)"
            value={teamQuery}
            onChange={(e) => setTeamQuery(e.target.value)}
            prefix={<SearchOutlined />}
            size="large"
          />

          <RangePicker
            style={{ width: '100%' }}
            size="large"
            value={dateRange}
            onChange={(dates) => setDateRange(dates || [null, null])}
            placeholder={['Start Date', 'End Date']}
          />

          <Button
            type="primary"
            size="large"
            block
            onClick={handleSearch}
            loading={loading}
            icon={<SearchOutlined />}
          >
            Search Games
          </Button>
        </Space>

        {searchResults.length > 0 && (
          <List
            dataSource={searchResults}
            loading={loading}
            renderItem={(game) => (
              <List.Item
                key={game.id}
                actions={[
                  <Button
                    type="primary"
                    onClick={() => handleSelectGame(game.id)}
                    loading={loadingGameDetails && selectedGameId === game.id}
                  >
                    Select
                  </Button>,
                ]}
              >
                <List.Item.Meta
                  avatar={<TrophyOutlined style={{ fontSize: 24 }} />}
                  title={
                    <Space>
                      <Text strong>{game.home_team}</Text>
                      <Text type="secondary">vs</Text>
                      <Text strong>{game.away_team}</Text>
                    </Space>
                  }
                  description={
                    <Space>
                      <Tag icon={<CalendarOutlined />} color="blue">
                        {dayjs(game.date).format('MMM D, YYYY')}
                      </Tag>
                      {game.competition && (
                        <Tag color="green">{game.competition}</Tag>
                      )}
                      {game.status && (
                        <Tag color={getStatusColor(game.status)}>
                          {game.status.toUpperCase()}
                        </Tag>
                      )}
                    </Space>
                  }
                />
              </List.Item>
            )}
          />
        )}

        {!loading && searchResults.length === 0 && (teamQuery || dateRange[0]) && (
          <Text type="secondary" style={{ textAlign: 'center', display: 'block' }}>
            No games found. Try adjusting your search criteria.
          </Text>
        )}
      </Space>
    </Modal>
  );
};
